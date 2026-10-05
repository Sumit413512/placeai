from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Job, MockInterview, StudentProfile, User
from app.student_entitlements import student_access_status

TRIAL_DEMO_COMPANY_NAME = "TechNova Solutions — Demo"
TRIAL_DEMO_JOB_TITLE = "PlaceAI TechNova Demo Assessment"


def is_trial_demo_job(job: Job | None) -> bool:
    if job is None or job.visibility != "public" or job.recruiter is None:
        return False
    return (
        (job.recruiter.company_name or "").strip() == TRIAL_DEMO_COMPANY_NAME
        and (job.title or "").strip() == TRIAL_DEMO_JOB_TITLE
    )


def trial_demo_attempt_count(profile: StudentProfile, job: Job, db: Session) -> int:
    return (
        db.query(MockInterview)
        .filter(
            MockInterview.student_id == profile.id,
            MockInterview.job_id == job.id,
        )
        .count()
    )


def trial_demo_access_state(
    user: User,
    profile: StudentProfile,
    job: Job,
    db: Session,
) -> dict:
    access = student_access_status(user, db)
    attempts = trial_demo_attempt_count(profile, job, db) if is_trial_demo_job(job) else 0

    if not is_trial_demo_job(job):
        return {
            "is_trial_demo": False,
            "can_start": bool(access["premium_access"]),
            "attempts_used": 0,
            "free_attempts_remaining": 0,
            "access_mode": access["access_mode"],
        }

    if access["access_mode"] in {"premium", "campus_sponsored"}:
        return {
            "is_trial_demo": True,
            "can_start": True,
            "attempts_used": attempts,
            "free_attempts_remaining": None,
            "access_mode": access["access_mode"],
            "access_note": "Included with your paid or institution-sponsored PlaceAI access.",
        }

    can_start = bool(access["premium_access"])
    note = (
        "Repeat demo assessments are included during your active trial."
        if can_start
        else "Your trial has ended. Purchase PlaceAI or join through an institution contract to continue."
    )
    return {
        "is_trial_demo": True,
        "can_start": can_start,
        "attempts_used": attempts,
        "free_attempts_remaining": None if can_start else 0,
        "access_mode": access["access_mode"],
        "access_note": note,
    }


def enforce_trial_demo_start(
    user: User,
    profile: StudentProfile,
    job: Job,
    db: Session,
) -> dict:
    state = trial_demo_access_state(user, profile, job, db)
    if not state["is_trial_demo"]:
        return state
    if state["access_mode"] in {"premium", "campus_sponsored"}:
        return state
    if state["can_start"]:
        return state

    raise HTTPException(
        status_code=402,
        detail={
            "code": "PREMIUM_REQUIRED",
            "message": (
                "Your trial has ended. Purchase a PlaceAI student plan or continue through "
                "an institution-sponsored PlaceAI contract to unlock further attempts."
            ),
            "attempts_used": state["attempts_used"],
            "free_attempts_remaining": state["free_attempts_remaining"],
        },
    )
