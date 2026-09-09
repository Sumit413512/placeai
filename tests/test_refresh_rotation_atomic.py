from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(
        email="refresh.atomic@placeai.example.com",
        username="refreshatomic",
        hashed_password=get_hashed_password("AtomicRefresh123!"),
        role=UserRole.student,
        email_verified=True,
    ))
    db.commit()
    db.close()


def test_atomic_refresh_route_is_exposed():
    response = client.post("/auth/refresh", json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token is required"


def test_atomic_refresh_endpoint_uses_database_row_lock():
    source = open("app/routers/auth_refresh_atomic.py", encoding="utf-8").read()
    app_source = open("app/app.py", encoding="utf-8").read()
    assert ".with_for_update()" in source
    assert "RefreshSession.jti" in source
    assert "session.revoked_at is not None" in source
    assert "revoke_jti=session.jti" in source
    assert 'getattr(route, "path", "") != "/auth/refresh"' in app_source
    assert "app.include_router(auth_refresh_atomic.router)" in app_source


def test_refresh_token_remains_single_use_in_normal_rotation():
    login = client.post("/auth/login-json", json={
        "email": "refresh.atomic@placeai.example.com",
        "password": "AtomicRefresh123!",
    })
    assert login.status_code == 200, login.text
    original_refresh = login.cookies.get("placeai_refresh")
    assert original_refresh

    rotated = client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert rotated.status_code == 200, rotated.text
    successor = rotated.cookies.get("placeai_refresh")
    assert successor and successor != original_refresh

    replay = client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401

    successor_refresh = client.post("/auth/refresh", json={"refresh_token": successor})
    assert successor_refresh.status_code == 200, successor_refresh.text
