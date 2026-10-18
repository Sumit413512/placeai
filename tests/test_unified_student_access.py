"""Shared student tools must never imply shared institutional data or admin rights."""
from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.dependencies import require_institution_admin
from app.models import Organization, StudentProfile, User, UserRole, utcnow
from app.roadmap_access import ensure_roadmap_access
from app.routers import auth, billing
from app.student_entitlements import ensure_student_premium_access
from app.utils import get_hashed_password


@pytest.mark.parametrize("college_linked", [False, True])
def test_old_and_new_students_share_tools_without_buying_access(monkeypatch, college_linked):
    monkeypatch.setattr(get_settings(), "student_unified_access", True)
    monkeypatch.setattr(get_settings(), "environment", "development")
    engine = create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        org = Organization(name="Private college",slug="private-college",is_active=True)
        db.add(org); db.flush()
        user = User(email="shared-tools@example.com",username="shared-tools",role=UserRole.student,
                    hashed_password=get_hashed_password("Isolated student verification 2026!",check_breach=False),
                    email_verified=True,created_at=utcnow()-timedelta(days=90),
                    organization_id=org.id if college_linked else None)
        db.add(user); db.flush()
        profile = StudentProfile(user_id=user.id,organization_id=user.organization_id,is_verified=college_linked)
        db.add(profile); db.commit()
        status = ensure_student_premium_access(user,db)
        assert status["premium_access"] and not status["payment_required"]
        assert status["student_kind"] == "student" and status["access_mode"] == "student_workspace"
        assert status["trial_ends_at"] is None
        assert status["campus_access"] is college_linked
        assert ensure_roadmap_access(user,db)["allowed"]
    application = FastAPI()
    application.include_router(auth.router); application.include_router(billing.router)
    def database():
        with sessions() as db:
            yield db
    application.dependency_overrides[get_db] = database
    @application.get("/private-admin",dependencies=[Depends(require_institution_admin)])
    def private_admin():
        return {"private":True}
    with TestClient(application) as client:
        response = client.post('/auth/login-json',json={"email":"shared-tools@example.com","password":"Isolated student verification 2026!"})
        assert response.status_code == 200
        headers = {"Authorization":"Bearer "+response.json()["access_token"]}
        assert client.get('/billing/status',headers=headers).json()["career_roadmap"]["allowed"]
        plans = client.get('/billing/plans',headers=headers).json()
        assert plans["plans"] == [] and plans["feature_unlocks"] == [] and not plans["checkout_enabled"]
        assert client.post('/billing/checkout',headers=headers).status_code == 409
        assert client.get('/private-admin',headers=headers).status_code == 403
        assert client.get('/billing/status').status_code == 401
    engine.dispose()
