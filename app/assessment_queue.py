"""Durable grading admission. PostgreSQL serializes admission across all workers."""
import json
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.models import AssessmentJob, AssessmentQueueControl, utcnow

MAX_ATTEMPTS = 24
LEASE_SECONDS = 180


def pending(job):
    return {"interview_id": job.interview_id, "analysis_status": "pending",
            "queued": True, "queue_status": job.state, "retry_after_seconds": 10,
            "status_url": f"/mock-interview/{job.interview_id}/result"}


def enqueue(db, interview, user, body):
    """First submission wins, including simultaneous duplicate submissions."""
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


def claim(db, concurrency, starts_per_minute):
    now = utcnow()
    control = db.query(AssessmentQueueControl).filter_by(id=1).with_for_update().one()
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
