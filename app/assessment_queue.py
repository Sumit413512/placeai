"""Durable grading admission. PostgreSQL serializes admission across all workers."""
import json
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import answer_recording
from app.models import AssessmentJob, AssessmentQueueControl, utcnow

MAX_ATTEMPTS = 24
LEASE_SECONDS = 180


def pending(job):
    return {"interview_id": job.interview_id, "analysis_status": "pending",
            "queued": True, "queue_status": job.state, "retry_after_seconds": 10,
            "expected_within_hours": 24,
            "status_url": f"/mock-interview/{job.interview_id}/result"}


def _enforce_spoken_contract(db, interview, body):
    """Fail closed if a full-assessment client substitutes text for required audio.

    Older/in-flight assessments may have Resume/Project, Role/JD and Situational questions stored
    as text because their audio response mode was historically inferred by the browser.
    The server-side answer policy is authoritative: materialize that inferred mode in
    the same locked transaction and require a sealed recording before queue admission.
    Practice rounds are deliberately excluded even when they contain a situational item.
    """
    try:
        questions = json.loads(interview.questions_json or "[]")
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, "Interview question set is unavailable") from exc
    if not isinstance(questions, list) or not questions:
        raise HTTPException(409, "Interview question set is unavailable")
    if not answer_recording.is_full_assessment_questions(questions):
        return

    changed = answer_recording.materialize_post_hr_modes(questions)
    effective_spoken = any(
        answer_recording.response_mode(question) in {"audio", "video"}
        for question in questions
        if isinstance(question, dict)
    )
    if not effective_spoken:
        return

    submitted = {answer.question_id: answer for answer in body.answers}
    question_ids = {
        question.get("question_id") for question in questions
        if isinstance(question, dict) and isinstance(question.get("question_id"), int)
    }
    if set(submitted) != question_ids:
        raise HTTPException(422, "Answers must match the server-issued interview question set")

    # response_mode() recognizes legacy standardized spoken records even before the
    # explicit metadata is persisted. Text is never accepted as a substitute for
    # those required spoken answers.
    answer_recording.sealed_answers(db, interview, questions, submitted)
    if changed:
        interview.questions_json = json.dumps(questions)
        db.flush()


def enqueue(db, interview, user, body):
    """First valid submission wins, including simultaneous duplicate submissions."""
    _enforce_spoken_contract(db, interview, body)
    existing = db.get(AssessmentJob, interview.id)
    if existing:
        return pending(existing)
    job = AssessmentJob(interview_id=interview.id, user_id=user.id,
                        payload_json=body.model_dump_json())
    try:
        # Flush the unique job before changing answers; a losing duplicate cannot
        # overwrite the winning submission in either table.
        db.add(job)
        db.flush()
        interview.answers_json = json.dumps([answer.model_dump() for answer in body.answers])
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(AssessmentJob, interview.id)
        if not existing:
            raise
        return pending(existing)
    return pending(job)


def _control_for_update(db, now):
    """Return the singleton admission row, recreating it if production data drift removed it.

    Migration 0016 seeds id=1, but queue safety must not depend forever on that one
    historical insert. The nested transaction makes concurrent worker bootstrap safe:
    exactly one insert wins while the others recover and lock the same row.
    """
    control = (
        db.query(AssessmentQueueControl)
        .filter_by(id=1)
        .with_for_update()
        .one_or_none()
    )
    if control is not None:
        return control

    try:
        with db.begin_nested():
            control = AssessmentQueueControl(
                id=1,
                window_started_at=now,
                starts_in_window=0,
            )
            db.add(control)
            db.flush()
    except IntegrityError:
        # Another worker restored the singleton first. The outer transaction remains
        # usable because the conflict was isolated to the SAVEPOINT above.
        pass

    return (
        db.query(AssessmentQueueControl)
        .filter_by(id=1)
        .with_for_update()
        .one()
    )


def claim(db, concurrency, starts_per_minute):
    now = utcnow()
    control = _control_for_update(db, now)
    if control.window_started_at <= now - timedelta(minutes=1):
        control.window_started_at = now
        control.starts_in_window = 0
    active = db.query(AssessmentJob).filter(
        AssessmentJob.state == "running", AssessmentJob.lease_until > now).count()
    if active >= concurrency or control.starts_in_window >= starts_per_minute:
        db.commit()
        return None
    job = db.query(AssessmentJob).filter(
        AssessmentJob.available_at <= now,
        or_(AssessmentJob.state.in_(["queued", "retrying"]),
            (AssessmentJob.state == "running") & (AssessmentJob.lease_until <= now)),
    ).order_by(AssessmentJob.available_at, AssessmentJob.created_at).with_for_update(skip_locked=True).first()
    if not job:
        db.commit()
        return None
    if job.attempts >= MAX_ATTEMPTS:
        job.state = "failed"
        job.error_code = "ANALYSIS_RETRY_LIMIT"
        db.commit()
        return None
    job.state = "running"
    job.attempts += 1
    job.lease_token = str(uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    control.starts_in_window += 1
    result = (job.interview_id, job.user_id, job.payload_json, job.lease_token)
    db.commit()
    return result


def heartbeat(db, interview_id, token):
    updated = db.query(AssessmentJob).filter_by(
        interview_id=interview_id, state="running", lease_token=token,
    ).filter(AssessmentJob.lease_until > utcnow()).update(
        {"lease_until": utcnow() + timedelta(seconds=LEASE_SECONDS)}, synchronize_session=False)
    db.commit()
    return bool(updated)


def assert_lease(db):
    """Fence stale workers before they persist final scores."""
    identity = db.info.get("assessment_lease")
    if not identity:
        return
    interview_id, token = identity
    job = db.query(AssessmentJob).filter_by(interview_id=interview_id).with_for_update().populate_existing().one()
    if job.state != "running" or job.lease_token != token or job.lease_until <= utcnow():
        raise HTTPException(409, "Analysis lease expired; your submission remains saved")


def finish(db, interview_id, token, complete, error_code=None):
    job = db.query(AssessmentJob).filter_by(interview_id=interview_id).with_for_update().one()
    if job.state != "running" or job.lease_token != token:
        db.rollback()
        return
    job.state = "complete" if complete else "failed" if job.attempts >= MAX_ATTEMPTS else "retrying"
    job.error_code = None if complete else "ANALYSIS_RETRY_LIMIT" if job.state == "failed" else error_code or "ANALYSIS_TEMPORARILY_UNAVAILABLE"
    delay = 900 if error_code in {"VIDEO_PROVIDER_CAPACITY", "AI_PROVIDER_CAPACITY"} else min(300, 15 * 2 ** (job.attempts - 1))
    job.available_at = utcnow() + timedelta(seconds=delay)
    job.lease_until = None
    job.lease_token = None
    db.commit()
