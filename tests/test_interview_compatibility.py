from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import ApprovalStatus, Job, MockInterview, RecruiterProfile, StudentProfile, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    student_user = User(
        email="compat.student@placeai.example.com",
        username="compatstudent",
        hashed_password=get_hashed_password("StudentPass123!"),
        role=UserRole.student,
        email_verified=True,
    )
    recruiter_user = User(
        email="compat.recruiter@placeai.example.com",
        username="compatrecruiter",
        hashed_password=get_hashed_password("RecruiterPass123!"),
        role=UserRole.recruiter,
        email_verified=True,
    )
    db.add_all([student_user, recruiter_user])
    db.flush()
    student = StudentProfile(
        user_id=student_user.id,
        full_name="Compatibility Student",
        degree="B.Tech",
        branch="Computer Science",
    )
    recruiter = RecruiterProfile(
        user_id=recruiter_user.id,
        company_name="PlaceAI Test Labs",
        is_verified=True,
    )
    db.add_all([student, recruiter])
    db.flush()
    job = Job(
        recruiter_id=recruiter.id,
        title="Graduate Backend Engineer",
        description="Build reliable APIs and production services using Python and SQL.",
        required_skills=["Python", "SQL"],
        preferred_roles=["Backend Developer"],
        visibility="public",
        approval_status=ApprovalStatus.approved,
        is_active=True,
    )
    db.add(job)
    db.flush()
    db.add_all([
        MockInterview(
            student_id=student.id,
            job_id=job.id,
            questions_json=json.dumps([{"question_id": 1, "question": "Draft question"}]),
            answers_json="[]",
            evaluation_json=None,
            overall_score=None,
            overall_feedback=None,
        ),
        MockInterview(
            student_id=student.id,
            job_id=job.id,
            questions_json=json.dumps([{"question_id": 1, "question": "Historical question"}]),
            answers_json=json.dumps([{"question_id": 1, "answer": "Historical answer"}]),
            evaluation_json=json.dumps([{"question_id": 1, "score": 70, "feedback": "Historical list format"}]),
            overall_score=70,
            overall_feedback="Historical feedback",
        ),
        MockInterview(
            student_id=student.id,
            job_id=job.id,
            questions_json=json.dumps([{"question_id": 1, "question": "Current question"}]),
            answers_json=json.dumps([{"question_id": 1, "answer": "Current answer"}]),
            evaluation_json=json.dumps({
                "dimensions": {"clarity": 82},
                "evaluations": [{"question_id": 1, "score": 82, "feedback": "Current dict format"}],
            }),
            overall_score=82,
            overall_feedback="Current feedback",
        ),
    ])
    db.commit()
    db.close()


def student_token() -> str:
    response = client.post("/auth/login-json", json={
        "email": "compat.student@placeai.example.com",
        "password": "StudentPass123!",
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_legacy_generation_and_evaluation_are_retired_for_students():
    token = student_token()
    generation = client.post("/ai/interview/questions", headers=auth(token), json={"job_id": "anything"})
    evaluation = client.post("/ai/interview/evaluate", headers=auth(token), json={"job_id": "anything", "answers": []})
    assert generation.status_code == 410
    assert evaluation.status_code == 410
    assert "/mock-interview/start" in generation.json()["detail"]
    assert "/mock-interview/evaluate" in evaluation.json()["detail"]


def test_retired_routes_still_require_student_authentication():
    generation = client.post("/ai/interview/questions", json={"job_id": "anything"})
    evaluation = client.post("/ai/interview/evaluate", json={"job_id": "anything", "answers": []})
    assert generation.status_code in {401, 403}
    assert evaluation.status_code in {401, 403}


def test_completed_history_excludes_drafts_and_accepts_historical_json_shapes():
    token = student_token()

    legacy_history = client.get("/ai/interviews", headers=auth(token))
    assert legacy_history.status_code == 200, legacy_history.text
    assert len(legacy_history.json()) == 2
    assert all(item["overall_score"] is not None for item in legacy_history.json())

    db = SessionLocal()
    try:
        rows = db.query(MockInterview).filter(MockInterview.overall_score.isnot(None)).order_by(MockInterview.overall_score.asc()).all()
        old_row = rows[0]
        current_row = rows[-1]
        old_id = old_row.id
        current_id = current_row.id
    finally:
        db.close()

    old_detail = client.get(f"/ai/interviews/{old_id}", headers=auth(token))
    assert old_detail.status_code == 200, old_detail.text
    assert isinstance(old_detail.json()["evaluations"], list)
    assert old_detail.json()["evaluations"][0]["score"] == 70

    current_detail = client.get(f"/ai/interviews/{current_id}", headers=auth(token))
    assert current_detail.status_code == 200, current_detail.text
    assert current_detail.json()["evaluations"][0]["score"] == 82

    canonical = client.get("/mock-interview/history", headers=auth(token))
    assert canonical.status_code == 200, canonical.text
    assert len(canonical.json()) == 2
    by_score = {item["overall_score"]: item for item in canonical.json()}
    assert by_score[70]["dimensions"] == {}
    assert by_score[82]["dimensions"]["clarity"] == 82


def test_openapi_marks_legacy_write_surface_deprecated_and_keeps_canonical_coach():
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/ai/interview/questions"]["post"]["deprecated"] is True
    assert paths["/ai/interview/evaluate"]["post"]["deprecated"] is True
    assert "/mock-interview/start" in paths
    assert "/mock-interview/evaluate" in paths
