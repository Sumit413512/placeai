"""Verified, idempotent delivery of completed student assessment reports."""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.email_delivery import send_transactional_email, transactional_email_configured
from app.models import AuditEvent, GoogleIdentity, Job, MockInterview, User, utcnow
from app.trial_demo_access import is_trial_demo_job

LOGGER = logging.getLogger("placeai.assessment_report_email")
SENT_ACTION = "assessment.report_email.sent"
FAILED_ACTION = "assessment.report_email.failed"


def eligible_recipient(db: Session, user: User, job: Job | None) -> str | None:
    """Return the account email only when Google verified it and this is not the public demo."""
    if (
        not user
        or not user.is_active
        or not user.email_verified
        or not user.email
        or is_trial_demo_job(job)
    ):
        return None
    linked_google = db.query(GoogleIdentity.subject).filter(GoogleIdentity.user_id == user.id).first()
    return user.email.strip().lower() if linked_google else None


def _report_body(interview: MockInterview, job: Job, result: dict) -> str:
    summary = result.get("score_summary") if isinstance(result.get("score_summary"), dict) else {}
    lines = [
        "Your PlaceAI assessment report is ready.",
        "",
        f"Role: {job.title}",
        f"Overall score: {result.get('overall_score', '—')}/100",
        f"Overall feedback: {result.get('overall_feedback') or 'See your report for detailed feedback.'}",
        "",
        "Score summary",
        f"Correct: {summary.get('correct', '—')}",
        f"Partially correct: {summary.get('partial', '—')}",
        f"Incorrect: {summary.get('incorrect', '—')}",
        f"Insufficient evidence: {summary.get('insufficient', '—')}",
        "",
    ]
    for heading, key in (
        ("Strengths", "strengths"),
        ("Areas to improve", "improvements"),
        ("Next practice plan", "next_practice_plan"),
    ):
        values = result.get(key) if isinstance(result.get(key), list) else []
        if values:
            lines.extend([heading, *(f"- {str(value)[:1000]}" for value in values[:12]), ""])

    evaluations = result.get("evaluations") if isinstance(result.get("evaluations"), list) else []
    if evaluations:
        lines.append("Question-by-question report")
        for item in evaluations[:50]:
            if not isinstance(item, dict):
                continue
            lines.extend([
                "",
                f"Q{item.get('question_id', '—')}. {str(item.get('question') or '')[:1000]}",
                f"Score: {item.get('score', '—')}/100",
                f"Your answer: {str(item.get('answer') or 'No answer submitted.')[:3000]}",
                f"Assessment: {str(item.get('feedback') or 'No detailed feedback returned.')[:2000]}",
            ])
            reference = str(item.get("correct_answer") or item.get("ideal_answer") or "").strip()
            if reference:
                lines.append(f"Reference answer: {reference[:3000]}")
            rubric = item.get("rubric") if isinstance(item.get("rubric"), dict) else {}
            if rubric:
                lines.append("Rubric: " + ", ".join(f"{key.replace('_', ' ')} {value}/100" for key, value in rubric.items()))
            for heading, key in (("What worked", "strengths"), ("Errors or gaps", "issues"), ("Missing points", "missing_points")):
                values = item.get(key) if isinstance(item.get(key), list) else []
                if values:
                    lines.append(f"{heading}: " + "; ".join(str(value)[:500] for value in values[:8]))
            better = str(item.get("better_answer_outline") or "").strip()
            if better:
                lines.append(f"Better answer structure: {better[:2000]}")

    settings = get_settings()
    lines.extend([
        "",
        "Open the private interactive report while signed in:",
        f"{settings.base_url}/mock-interview?result={interview.id}",
        "",
        "This report is private assessment feedback for the registered student account.",
    ])
    return "\n".join(lines)[:120_000]


def delivery_status(db: Session, interview_id: str) -> str:
    sent = db.query(AuditEvent.id).filter(
        AuditEvent.action == SENT_ACTION,
        AuditEvent.entity_type == "mock_interview",
        AuditEvent.entity_id == interview_id,
    ).first()
    return "sent" if sent else "pending"


def deliver_completed_report(db: Session, interview: MockInterview, user: User, job: Job, result: dict) -> str:
    """Send a completed report once. Failures stay retryable and never block result access."""
    recipient = eligible_recipient(db, user, job)
    settings = get_settings()
    if not recipient:
        return "not_eligible"
    if not transactional_email_configured(settings):
        return "not_configured"
    if result.get("analysis_status") != "complete" or interview.overall_score is None:
        return "not_ready"

    # Serialize delivery for this report across web and worker processes. The advisory
    # lock is transaction-scoped and contains no student data.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"assessment-report:{interview.id}"})
    if delivery_status(db, interview.id) == "sent":
        db.commit()
        return "sent"
    recent_failure = db.query(AuditEvent.id).filter(
        AuditEvent.action == FAILED_ACTION,
        AuditEvent.entity_type == "mock_interview",
        AuditEvent.entity_id == interview.id,
        AuditEvent.created_at >= utcnow() - timedelta(minutes=5),
    ).first()
    if recent_failure:
        db.commit()
        return "pending"

    outcome, reason = send_transactional_email(
        settings,
        recipient=recipient,
        subject=f"Your PlaceAI assessment report · {job.title}",
        body=_report_body(interview, job, result),
    )
    action = SENT_ACTION if outcome == "sent" else FAILED_ACTION
    db.add(AuditEvent(
        actor_user_id=user.id,
        organization_id=user.organization_id,
        action=action,
        entity_type="mock_interview",
        entity_id=interview.id,
        metadata_json=json.dumps({"outcome": outcome, "reason": reason}),
    ))
    db.commit()
    if outcome != "sent":
        LOGGER.warning("Assessment report email deferred reason=%s", reason or outcome)
        return "pending"
    return "sent"
