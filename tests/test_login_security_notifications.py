from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import AuditEvent, Notification, RefreshSession, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)

PLATFORM_EMAIL = "security.platform@placeai.example.com"
RECRUITER_EMAIL = "security.recruiter@placeai.example.com"
STUDENT_EMAIL = "security.student@placeai.example.com"
PASSWORD = "SecurityLoginPass123!"


def _ensure_user(email: str, username: str, role: UserRole) -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, username=username, hashed_password=get_hashed_password(PASSWORD), role=role, email_verified=True))
            db.commit()
    finally:
        db.close()


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user(PLATFORM_EMAIL, "security_platform", UserRole.platform_admin)
    _ensure_user(RECRUITER_EMAIL, "security_recruiter", UserRole.recruiter)
    _ensure_user(STUDENT_EMAIL, "security_student", UserRole.student)


def teardown_module() -> None:
    db = SessionLocal()
    try:
        user_ids = [row[0] for row in db.query(User.id).filter(User.email.in_([PLATFORM_EMAIL, RECRUITER_EMAIL, STUDENT_EMAIL])).all()]
        if user_ids:
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(Notification).filter(Notification.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(AuditEvent).filter(AuditEvent.actor_user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.email.in_([PLATFORM_EMAIL, RECRUITER_EMAIL, STUDENT_EMAIL])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_successful_role_login_is_audited() -> None:
    response = client.post("/auth/login-role", json={"email": STUDENT_EMAIL, "password": PASSWORD, "role": "student"})
    assert response.status_code == 200, response.text
    db = SessionLocal()
    try:
        student = db.query(User).filter(User.email == STUDENT_EMAIL).first()
        event = db.query(AuditEvent).filter(AuditEvent.actor_user_id == student.id, AuditEvent.action == "auth.login.success").order_by(AuditEvent.created_at.desc()).first()
        assert event is not None
        assert event.details["role"] == "student"
        assert event.details["provider"] == "password"
    finally:
        db.close()


def test_controlled_role_login_notifies_platform_admin_in_app() -> None:
    response = client.post("/auth/login-role", json={"email": RECRUITER_EMAIL, "password": PASSWORD, "role": "recruiter"})
    assert response.status_code == 200, response.text
    db = SessionLocal()
    try:
        platform = db.query(User).filter(User.email == PLATFORM_EMAIL).first()
        notification = db.query(Notification).filter(Notification.user_id == platform.id, Notification.category == "security").order_by(Notification.created_at.desc()).first()
        assert notification is not None
        assert "Recruiter" in notification.title or "Recruiter" in notification.message
        assert RECRUITER_EMAIL in notification.message
        assert notification.priority == "high"
    finally:
        db.close()
