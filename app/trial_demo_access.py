from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Job, MockInterview, StudentProfile, User
from app.student_entitlements import student_access_status

TRIAL_DEMO_COMPANY_NAME = "TechNova Solutions — Demo"
TRIAL_DEMO_JOB_TITLE = "PlaceAI TechNova Demo Assessment"
TRIAL_DEMO_FREE_ATTEMPTS = 1

# The live standardized assessment contract. Historical demo rows created before the
# private spoken-response rollout must not consume a student's one current free attempt.
# A completed historical attempt still counts, so this cannot be used to regain a free
# attempt after receiving a real result.
TRIAL_DEMO_CURRENT_QUESTION_COUNT = 50
TRIAL_DEMO_AUDIO_RESPONSES = 8
TRIAL_DEMO_VIDEO_RESPONSES = 4


def is_trial_demo_job(job: Job | None) -> bool:
    if job is None or job.visibility != "public" or job.recruiter is None:
        return False
    return (
        (job.recruiter.company_name or "").strip() == TRIAL_DEMO_COMPANY_NAME
        and (job.title or "").strip() == TRIAL_DEMO_JOB_TITLE
    )


def _counts_as_trial_attempt(interview: MockInterview) -> bool:
    """Count only completed attempts or attempts issued under the current contract.

    Before private spoken responses were server-issued, development/pilot demo rows could
    contain the 50-item assessment and four HR video questions but no explicit audio
    response modes. Those obsolete rows can no longer be completed under the current
    recording contract and should not permanently consume today's one-free-attempt grant.
    """
    if interview.overall_score is not None:
        return True

    try:
        questions = json.loads(interview.questions_json or "[]")
    except (TypeError, ValueError):
        return False
    if not isinstance(questions, list) or len(questions) != TRIAL_DEMO_CURRENT_QUESTION_COUNT:
        return False

    audio_count = sum(
        1
        for question in questions
        if isinstance(question, dict)
        and str(question.get("response_mode", "")).strip().lower() == "audio"
    )
    video_count = sum(
        1
        for question in questions
        if isinstance(question, dict)
        and str(question.get("answer_type", "")).strip().lower() == "video"
    )
    return (
        audio_count >= TRIAL_DEMO_AUDIO_RESPONSES
        and video_count >= TRIAL_DEMO_VIDEO_RESPONSES
    )


def trial_demo_attempt_count(profile: StudentProfile, job: Job, db: Session) -> int:
    rows = (
        db.query(MockInterview)
        .filter(
            MockInterview.student_id == profile.id,
            MockInterview.job_id == job.id,
        )
        .all()
    )
    return sum(1 for interview in rows if _counts_as_trial_attempt(interview))


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

    trial_active = access["access_mode"] == "trial" and bool(access["premium_access"])
    free_attempts_remaining = max(0, TRIAL_DEMO_FREE_ATTEMPTS - attempts) if trial_active else 0
    can_start = trial_active and free_attempts_remaining > 0

    if attempts >= TRIAL_DEMO_FREE_ATTEMPTS:
        note = (
            "You have used your one free TechNova demo assessment attempt. "
            "Purchase PlaceAI or continue through an institution-sponsored contract to attempt it again."
        )
    elif trial_active:
        note = "Your active trial includes one free TechNova demo assessment attempt."
    else:
        note = (
            "Your trial has ended. Purchase PlaceAI or join through an institution contract to continue."
        )

    return {
        "is_trial_demo": True,
        "can_start": can_start,
        "attempts_used": attempts,
        "free_attempts_remaining": free_attempts_remaining,
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

    if state["attempts_used"] >= TRIAL_DEMO_FREE_ATTEMPTS:
        message = (
            "You have already used your one free TechNova demo assessment attempt. "
            "Purchase a PlaceAI student plan or continue through an institution-sponsored PlaceAI contract "
            "to unlock further attempts."
        )
    else:
        message = (
            "Your trial has ended. Purchase a PlaceAI student plan or continue through "
            "an institution-sponsored PlaceAI contract to unlock the demo assessment."
        )

    raise HTTPException(
        status_code=402,
        detail={
            "code": "PREMIUM_REQUIRED",
            "message": message,
            "attempts_used": state["attempts_used"],
            "free_attempts_remaining": state["free_attempts_remaining"],
        },
    )