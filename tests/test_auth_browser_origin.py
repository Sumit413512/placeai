"""Browser attack regressions use an isolated database and synthetic credentials."""
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import auth
from app.utils import get_hashed_password

application = importlib.import_module("app.app")


@pytest.fixture
def browser_auth(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(User(email="origin-test@example.invalid", username="origin-test", role=UserRole.student,
                    hashed_password=get_hashed_password("IsolatedTestPass2026!")))
        db.commit()
    isolated = FastAPI()
    isolated.middleware("http")(application.security_headers)
    isolated.include_router(auth.router)
    @isolated.get("/private-test")
    def private_response():
        return {"private": True}
    def database():
        with sessions() as db:
            yield db
    isolated.dependency_overrides[get_db] = database
    monkeypatch.setattr(application.settings, "allowed_origins", ["https://www.placeai.in"])
    with TestClient(isolated, base_url="https://placeai.test") as client:
        yield client
    engine.dispose()


def credentials():
    return {"username": "origin-test@example.invalid", "password": "IsolatedTestPass2026!"}


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "https://placeai.test.attacker.example", ""])
def test_cross_origin_form_login_cannot_set_a_victim_session(browser_auth, origin):
    response = browser_auth.post("/auth/login", data=credentials(), headers={"Origin": origin})
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_ORIGIN_REJECTED"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("origin", ["https://placeai.test", "https://www.placeai.in", None])
def test_same_origin_configured_frontend_and_nonbrowser_login_work(browser_auth, origin):
    response = browser_auth.post("/auth/login", data=credentials(), headers={"Origin": origin} if origin else {})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "placeai_refresh=" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/auth/login-json", "/auth/login-role", "/auth/refresh", "/auth/logout", "/auth/google", "/auth/change-password"])
def test_foreign_origin_is_rejected_before_authentication_or_cookie_mutation(browser_auth, path):
    response = browser_auth.post(path, json={}, headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_browser_cross_site_request_without_origin_fails_closed(browser_auth):
    response = browser_auth.post("/auth/login", data=credentials(), headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_authenticated_responses_and_errors_are_not_browser_cacheable(browser_auth):
    for path in ["/private-test", "/missing-private-test"]:
        response = browser_auth.get(path, headers={"Authorization": "Bearer isolated-token"})
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
