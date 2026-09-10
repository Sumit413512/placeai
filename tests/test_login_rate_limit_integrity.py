from pathlib import Path

from fastapi.testclient import TestClient

from app.app import app
from app.database import SessionLocal
from app.models import RateLimitBucket

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)
RATE_EMAIL = "rate.limit.integrity@placeai.example.com"


def setup_function() -> None:
    db = SessionLocal()
    try:
        db.query(RateLimitBucket).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_role_login_uses_shared_login_rate_limit_bucket() -> None:
    source = (ROOT / "app/routers/access.py").read_text(encoding="utf-8")
    anchor = source.index("def login_for_selected_role")
    block = source[anchor:anchor + 1800]
    assert 'scope="login"' in block
    assert 'identifier=email' in block
    assert 'identifier=f"{body.role}:{email}"' not in block


def test_role_switching_cannot_multiply_login_attempt_budget() -> None:
    roles = ["student", "recruiter", "institution_admin", "platform_admin"]
    for index in range(12):
        response = client.post(
            "/auth/login-role",
            json={
                "email": RATE_EMAIL,
                "password": "DefinitelyWrongPassword123!",
                "role": roles[index % len(roles)],
            },
        )
        assert response.status_code == 401, response.text

    blocked = client.post(
        "/auth/login-role",
        json={
            "email": RATE_EMAIL,
            "password": "DefinitelyWrongPassword123!",
            "role": "student",
        },
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After")
