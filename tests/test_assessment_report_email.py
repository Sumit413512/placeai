from types import SimpleNamespace
from datetime import timedelta

from app import assessment_report_email as reports
from app.models import AuditEvent, GoogleIdentity, utcnow
from app.trial_demo_access import TRIAL_DEMO_COMPANY_NAME, TRIAL_DEMO_JOB_TITLE
from test_hr_video import exam  # noqa: F401


def _settings():
    return SimpleNamespace(
        app_name="PlaceAI", base_url="https://www.placeai.in",
        smtp_host="smtp.example.com", smtp_port=587, smtp_user="", smtp_password="",
        smtp_from="reports@placeai.in", smtp_tls=True, brevo_api_key="",
    )


def _completed(exam):  # noqa: F811
    exam.user.email_verified = True
    exam.interview.overall_score = 82
    exam.db.add(GoogleIdentity(subject="google-student", user_id=exam.user.id))
    exam.db.commit()
    return {
        "analysis_status": "complete", "overall_score": 82,
        "overall_feedback": "Strong role knowledge.",
        "score_summary": {"correct": 31, "partial": 10, "incorrect": 5, "insufficient": 4},
        "strengths": ["Clear reasoning"], "improvements": ["Use more measurable outcomes"],
        "next_practice_plan": ["Repeat two coding exercises"],
        "evaluations": [{"question_id": 1, "question": "Explain your approach", "score": 80,
                         "feedback": "Good structure", "better_answer_outline": "State assumptions first"}],
    }


def test_verified_google_student_receives_complete_report_exactly_once(exam, monkeypatch):  # noqa: F811
    GoogleIdentity.__table__.create(exam.engine)
    result = _completed(exam)
    deliveries = []
    monkeypatch.setattr(reports, "get_settings", _settings)
    monkeypatch.setattr(reports, "send_transactional_email", lambda settings, **message: deliveries.append(message) or ("sent", None))

    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "sent"
    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "sent"
    assert len(deliveries) == 1
    assert deliveries[0]["recipient"] == exam.user.email
    assert "Question-by-question report" in deliveries[0]["body"]
    assert f"?result={exam.interview.id}" in deliveries[0]["body"]


def test_demo_and_unverified_accounts_never_receive_report_email(exam, monkeypatch):  # noqa: F811
    GoogleIdentity.__table__.create(exam.engine)
    result = _completed(exam)
    sent = []
    monkeypatch.setattr(reports, "get_settings", _settings)
    monkeypatch.setattr(reports, "send_transactional_email", lambda *args, **kwargs: sent.append(kwargs) or ("sent", None))

    exam.user.email_verified = False
    exam.db.commit()
    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "not_eligible"
    exam.user.email_verified = True
    exam.job.visibility = "public"
    exam.job.title = TRIAL_DEMO_JOB_TITLE
    exam.job.recruiter.company_name = TRIAL_DEMO_COMPANY_NAME
    exam.db.commit()
    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "not_eligible"
    assert sent == []


def test_failed_mail_delivery_remains_retryable(exam, monkeypatch):  # noqa: F811
    GoogleIdentity.__table__.create(exam.engine)
    result = _completed(exam)
    outcomes = iter([("failed", "smtp_unavailable"), ("sent", None)])
    monkeypatch.setattr(reports, "get_settings", _settings)
    monkeypatch.setattr(reports, "send_transactional_email", lambda *args, **kwargs: next(outcomes))

    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "pending"
    failed = exam.db.query(AuditEvent).filter(AuditEvent.action == reports.FAILED_ACTION).one()
    failed.created_at = utcnow() - timedelta(minutes=6)
    exam.db.commit()
    assert reports.deliver_completed_report(exam.db, exam.interview, exam.user, exam.job, result) == "sent"
    assert reports.delivery_status(exam.db, exam.interview.id) == "sent"
