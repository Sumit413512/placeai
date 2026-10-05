from datetime import timedelta

import pytest
from fastapi import HTTPException

from app import assessment_queue as queue
from app.models import AssessmentJob, AssessmentQueueControl, MockInterview, utcnow
from app.routers import mock_interview_v2 as exams, mock_interview
from test_hr_video import body, exam  # noqa: F401 - shared isolated exam fixture


@pytest.fixture
def queued(exam):
    AssessmentJob.__table__.create(exam.engine)
    AssessmentQueueControl.__table__.create(exam.engine)
    exam.db.add(AssessmentQueueControl(id=1, window_started_at=utcnow(), starts_in_window=0))
    exam.db.commit()
    return exam


def test_first_submission_is_immutable(queued):
    queue.enqueue(queued.db, queued.interview, queued.user, body(queued, "Original answer"))
    queue.enqueue(queued.db, queued.interview, queued.user, body(queued, "Replacement"))
    job = queued.db.get(AssessmentJob, queued.interview.id)
    assert "Original answer" in job.payload_json
    assert "Replacement" not in queued.interview.answers_json
    assert queued.interview.overall_score is None


def test_enqueue_route_does_not_call_providers_and_hides_partial_scores(queued, monkeypatch):
    monkeypatch.setattr(exams.get_settings(), "assessment_queue_enabled", True)
    monkeypatch.setattr(exams, "evaluate_inline", lambda *_: pytest.fail("Submission must not call AI"))
    response = exams.evaluate_mock_interview_v2(body(queued), queued.user, queued.db)
    assert response.status_code == 202
    queued.interview.evaluation_json = '{"overall_score":99}'
    queued.db.commit()
    status = exams.saved_interview_result(queued.interview.id, queued.user, queued.db)
    assert status["queued"] and status["result"] is None
    assert mock_interview.mock_interview_history(queued.user, queued.db)[0]["overall_score"] is None
    assert exams.retry_saved_interview(queued.interview.id, queued.user, queued.db).status_code == 202


def test_enqueue_rejects_foreign_exam_and_changed_question_set(queued, monkeypatch):
    monkeypatch.setattr(exams.get_settings(), "assessment_queue_enabled", True)
    wrong = body(queued)
    wrong.answers = wrong.answers[:-1]
    with pytest.raises(HTTPException) as error:
        exams.evaluate_mock_interview_v2(wrong, queued.user, queued.db)
    assert error.value.status_code == 422
    wrong.interview_id = "someone-elses-exam"
    with pytest.raises(HTTPException) as error:
        exams.evaluate_mock_interview_v2(wrong, queued.user, queued.db)
    assert error.value.status_code == 404
    assert queued.db.query(AssessmentJob).count() == 0


def test_global_concurrency_and_start_budget(queued):
    for number in range(3):
        interview = MockInterview(id=f"exam-{number}", student_id=queued.profile.id,
                                  job_id=queued.job.id, questions_json="[]", answers_json="[]")
        queued.db.add(interview)
        queued.db.flush()
        queued.db.add(AssessmentJob(interview_id=interview.id, user_id=queued.user.id, payload_json="{}"))
    queued.db.commit()
    first = queue.claim(queued.db, 1, 2)
    assert first
    assert queue.claim(queued.db, 1, 2) is None
    queue.finish(queued.db, first[0], first[3], True)
    second = queue.claim(queued.db, 1, 2)
    assert second
    queue.finish(queued.db, second[0], second[3], True)
    assert queue.claim(queued.db, 1, 2) is None


def test_expired_worker_cannot_save_or_acknowledge(queued):
    queue.enqueue(queued.db, queued.interview, queued.user, body(queued))
    old = queue.claim(queued.db, 1, 10)
    job = queued.db.get(AssessmentJob, old[0])
    job.lease_until = utcnow() - timedelta(seconds=1)
    queued.db.commit()
    assert not queue.heartbeat(queued.db, old[0], old[3])
    new = queue.claim(queued.db, 1, 10)
    assert new[3] != old[3]
    queued.db.info["assessment_lease"] = (old[0], old[3])
    with pytest.raises(HTTPException):
        queue.assert_lease(queued.db)
    queued.db.rollback()
    queue.finish(queued.db, old[0], old[3], True)
    assert queued.db.get(AssessmentJob, old[0]).state == "running"
    queue.finish(queued.db, new[0], new[3], True)
    assert queued.db.get(AssessmentJob, old[0]).state == "complete"


def test_provider_failure_has_bounded_retries_and_retains_answers(queued):
    queue.enqueue(queued.db, queued.interview, queued.user, body(queued))
    for attempt in range(queue.MAX_ATTEMPTS):
        job = queued.db.get(AssessmentJob, queued.interview.id)
        job.available_at = utcnow() - timedelta(seconds=1)
        queued.db.commit()
        item = queue.claim(queued.db, 4, 100)
        assert item
        queue.finish(queued.db, item[0], item[3], False)
    assert job.state == "failed"
    assert job.error_code == "ANALYSIS_RETRY_LIMIT"
    assert job.payload_json and queued.interview.answers_json
    assert queued.interview.overall_score is None
    assert queue.claim(queued.db, 4, 100) is None
