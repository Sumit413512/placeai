from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.array_readiness_models import ArrayReadiness
from app.database import Base, get_db
from app.dependencies import require_institution_admin, require_student
from app.models import Organization, OrganizationType, StudentProfile, User, UserRole
from app.routers.array_readiness import router


def test_array_readiness_tracks_assignments_and_keeps_other_students_private():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[Organization.__table__, User.__table__,
                                            StudentProfile.__table__, ArrayReadiness.__table__])
    with Session(engine, expire_on_commit=False) as db:
        for identifier in ("college-a", "college-b"):
            db.add(Organization(id=identifier, name=identifier, slug=identifier,
                                organization_type=OrganizationType.institution, is_active=True))
        student = User(id="student", username="student", email="s@example.invalid", hashed_password="fixture",
                       role=UserRole.student, organization_id="college-a")
        admin = User(id="admin", username="admin", email="a@example.invalid", hashed_password="fixture",
                     role=UserRole.institution_admin, organization_id="college-a")
        foreign_admin = User(id="foreign", username="foreign", email="f@example.invalid", hashed_password="fixture",
                             role=UserRole.institution_admin, organization_id="college-b")
        db.add_all([student, admin, foreign_admin])
        db.flush()
        db.add(StudentProfile(user_id=student.id, organization_id="college-a"))
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def get_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[require_student] = lambda: student
    actor = [foreign_admin]
    app.dependency_overrides[require_institution_admin] = lambda: actor[0]
    with TestClient(app) as client:
        base = "/array-readiness"
        answer = base + "/me/answers"
        report = base + "/institution"
        assign = report + "/assignments/student"
        actual = client.get(base + "/me").json()
        assert actual["step"] == "diagnostic" and "correct" not in actual["question"]
        assert client.post(answer, json={"track": "personal", "step": "followup", "choice": 3}).status_code == 409
        assert client.post(answer, json={"track": "personal", "step": "diagnostic", "choice": 1}).status_code == 200
        assert client.put(assign).status_code == 404
        assert client.get(report).json()["students"] == []
        actor[0] = admin
        assert client.get(report).json()["started"] == 0
        assert client.put(assign).status_code == 204
        assert client.get(base + "/me").json()["step"] == "diagnostic"
        assert client.post(answer, json={"track": "personal", "step": "practice", "choice": 2}).status_code == 409

        for step, choice in (("diagnostic", 0), ("practice", 2), ("followup", 3)):
            payload = {"track": "college-a", "step": step, "choice": choice}
            response = client.post(answer, json=payload)
            assert response.status_code == 200, response.text
            assert client.post(answer, json=payload).json() == response.json()
        assert client.post(answer, json={"track": "college-a", "step": "diagnostic", "choice": 1}).status_code == 409
        assert client.put(assign).status_code == 204
        cohort = client.get(report).json()
        assert (cohort["assigned"], cohort["started"], cohort["reassessed"], cohort["improved"]) == (1, 1, 1, 1)
        assert cohort["students"][0]["followup_correct"] is True
        assert client.get(report, params={"search": "_"}).json()["students"] == []
        actor[0] = foreign_admin
        assert client.get(report).json()["assigned"] == 0
    engine.dispose()
