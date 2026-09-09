from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_student
from app.models import MockInterview, StudentProfile, User
from app.schemas import MockInterviewDetailOut, MockInterviewHistoryOut

router = APIRouter(tags=["Interview Compatibility"])


def _student_profile(current_user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _json_list(raw: str | None, *, dict_key: str | None = None) -> list:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and dict_key:
        nested = value.get(dict_key, [])
        return nested if isinstance(nested, list) else []
    return []


def _evaluation_dict(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


@router.post("/ai/interview/questions", deprecated=True)
def retired_interview_questions(current_user: User = Depends(require_student)):
    del current_user
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy interview generation is retired. Use POST /mock-interview/start; "
            "PlaceAI now binds every interview to a server-issued interview_id."
        ),
    )


@router.post("/ai/interview/evaluate", deprecated=True)
def retired_interview_evaluate(current_user: User = Depends(require_student)):
    del current_user
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy interview scoring is retired. Use POST /mock-interview/evaluate with "
            "the server-issued interview_id so question text cannot be substituted by the client."
        ),
    )


@router.get("/ai/interviews", response_model=List[MockInterviewHistoryOut])
def completed_interview_history(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _student_profile(current_user, db)
    interviews = (
        db.query(MockInterview)
        .filter(
            MockInterview.student_id == profile.id,
            MockInterview.overall_score.isnot(None),
        )
        .order_by(MockInterview.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        MockInterviewHistoryOut(
            id=row.id,
            job_title=row.job.title if row.job else "Unknown Role",
            company_name=row.job.recruiter.company_name if row.job and row.job.recruiter else None,
            overall_score=row.overall_score,
            created_at=row.created_at,
        )
        for row in interviews
    ]


@router.get("/ai/interviews/{interview_id}", response_model=MockInterviewDetailOut)
def completed_interview_detail(
    interview_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _student_profile(current_user, db)
    row = (
        db.query(MockInterview)
        .filter(
            MockInterview.id == interview_id,
            MockInterview.student_id == profile.id,
            MockInterview.overall_score.isnot(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Mock interview log not found")
    return MockInterviewDetailOut(
        id=row.id,
        job_id=row.job_id,
        job_title=row.job.title if row.job else "Unknown Role",
        company_name=row.job.recruiter.company_name if row.job and row.job.recruiter else None,
        questions=_json_list(row.questions_json),
        answers=_json_list(row.answers_json),
        evaluations=_json_list(row.evaluation_json, dict_key="evaluations"),
        overall_score=row.overall_score,
        overall_feedback=row.overall_feedback,
        created_at=row.created_at,
    )


@router.get("/mock-interview/history")
def canonical_interview_history(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _student_profile(current_user, db)
    rows = (
        db.query(MockInterview)
        .filter(
            MockInterview.student_id == profile.id,
            MockInterview.overall_score.isnot(None),
        )
        .order_by(MockInterview.created_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for row in rows:
        evaluation = _evaluation_dict(row.evaluation_json)
        result.append({
            "id": row.id,
            "job_id": row.job_id,
            "job_title": row.job.title if row.job else "Role",
            "company_name": row.job.recruiter.company_name if row.job and row.job.recruiter else None,
            "overall_score": row.overall_score,
            "dimensions": evaluation.get("dimensions", {}),
            "overall_feedback": row.overall_feedback,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return result
