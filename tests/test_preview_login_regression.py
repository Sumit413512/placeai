from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Organization, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)


def test_institution_admin_role_login_accepts_symbol_password():
    Base.metadata.create_all(bind=engine)
    email = "preview-regression@placeai.example.com"
    password = "PlaceAI-Preview-2026!"
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "preview-regression").first()
        if not org:
            org = Organization(name="Preview Regression Institute", slug="preview-regression", is_active=True)
            db.add(org)
            db.flush()
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                username="preview_regression_admin",
                hashed_password=get_hashed_password(password),
                role=UserRole.institution_admin,
                organization_id=org.id,
                email_verified=True,
                is_active=True,
            )
            db.add(user)
        else:
            user.hashed_password = get_hashed_password(password)
            user.role = UserRole.institution_admin
            user.organization_id = org.id
            user.email_verified = True
            user.is_active = True
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/auth/login-role",
        json={"email": email, "password": password, "role": "institution_admin"},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("access_token")
