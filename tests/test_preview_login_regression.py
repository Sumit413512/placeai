from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.preview_seed import seed_preview_data

client = TestClient(app)


def test_exact_preview_seed_credentials_can_role_login(monkeypatch):
    Base.metadata.create_all(bind=engine)
    credentials = {
        "institution_admin": (
            "preview-tpo@placeai.example.com",
            "PlaceAIPreviewTPO2026",
        ),
        "student": (
            "preview-student@placeai.example.com",
            "PlaceAIPreviewStudent2026",
        ),
        "recruiter": (
            "preview-recruiter@placeai.example.com",
            "PlaceAIPreviewRecruiter2026",
        ),
    }
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("PREVIEW_SEED", "true")
    monkeypatch.setenv("PREVIEW_TPO_PASSWORD", credentials["institution_admin"][1])
    monkeypatch.setenv("PREVIEW_STUDENT_PASSWORD", credentials["student"][1])
    monkeypatch.setenv("PREVIEW_RECRUITER_PASSWORD", credentials["recruiter"][1])

    db = SessionLocal()
    try:
        seed_preview_data(db)
    finally:
        db.close()

    for role, (email, password) in credentials.items():
        response = client.post(
            "/auth/login-role",
            json={"email": email, "password": password, "role": role},
        )
        assert response.status_code == 200, (role, response.text)
        assert response.json().get("access_token"), role
