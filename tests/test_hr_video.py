from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import hr_video
from app.database import Base, get_db
from app.dependencies import get_current_user, require_student
from app.models import (
    AuditEvent, HRRecording, HRVideoChunk, Job, MockInterview, Organization,
    RecruiterProfile, StudentProfile, User, UserRole,
)
from app.routers import hr_recording, mock_interview, mock_interview_v2 as exams


@pytest.fixture
def exam(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[model.__table__ for model in (
        Organization, User, StudentProfile, RecruiterProfile, Job, MockInterview,
        HRRecording, HRVideoChunk, AuditEvent,
    )])
    db = Session(engine, expire_on_commit=False)
    clock = SimpleNamespace(now=datetime(2026, 10, 3, 10))
    monkeypatch.setattr(hr_video, "utcnow", lambda: clock.now)
    monkeypatch.setattr(exams, "utcnow", lambda: clock.now)
    org = Organization(id="org", name="Test institution", slug="test-institution")
    user = User(id="student", email="student@example.com", username="student", hashed_password="test-hash",
                role=UserRole.student, organization_id="org")
    recruiter = User(id="recruiter", email="recruiter@example.com", username="recruiter", hashed_password="test-hash",
                     role=UserRole.recruiter)
    profile = StudentProfile(id="profile", user_id=user.id, organization_id="org", full_name="Test student")
    recruiter_profile = RecruiterProfile(id="recruiter-profile", user_id=recruiter.id)
    job = Job(id="job", recruiter_id=recruiter_profile.id, title="Data analyst", description="Analyze data using SQL")
    questions = [{"question_id": number, "question": f"Explain a collaboration example {number}",
                  "section": "behavioral", "category": "hr", "difficulty": "medium", "answer_type": "video"}
                 for number in range(1, 5)]
    interview = MockInterview(id="interview", student_id=profile.id, job_id=job.id,
                              questions_json=json.dumps(questions), answers_json="[]", created_at=clock.now)
    recording = HRRecording(id="recording", interview_id=interview.id, expires_at=clock.now + timedelta(days=30))
    db.add_all([org, user, recruiter, profile, recruiter_profile, job, interview, recording])
    db.commit()
    value = SimpleNamespace(db=db, engine=engine, user=user, interview=interview, recording=recording,
                            clock=clock, questions=questions, profile=profile, job=job)
    yield value
    db.close()
    engine.dispose()


def begin(exam):
    hr_video.start_exam(exam.db, exam.recording, exam.interview)
    return hr_video.begin_recording(exam.db, exam.recording, exam.interview, "video/webm", True)


def seal(exam):
    begin(exam)
    hr_video.save_chunk(exam.db, exam.recording, exam.interview, 0, b"\x1a\x45\xdf\xa3test-video")
    for number in range(1, 5):
        exam.clock.now += timedelta(seconds=10)
        hr_video.advance_question(exam.db, exam.recording, exam.interview, number)
    hr_video.seal_recording(exam.db, exam.recording, 1)


def analysis(exam):
    return {"audio_usable": True, "video_usable": True, "summary": "Clear answers with relevant examples.",
            "answers": [{"question_id": number, "transcript": f"My answer to question {number}",
                         "answer_correctness": 80, "communication_clarity": 70, "english_fluency": 60,
                         "feedback": "Give a measurable outcome.", "strengths": ["Relevant example"],
                         "improvements": ["Explain the outcome"],
                         "evidence": [{"at_seconds": (number - 1) * 10 + 1, "observation": "Explains an example."}]}
                        for number in range(1, 5)]}


def body(exam, answer="[HR video response recorded]"):
    return exams.MockInterviewEvaluationV2(interview_id=exam.interview.id,
            answers=[{"question_id": q["question_id"], "answer": answer} for q in json.loads(exam.interview.questions_json)])


def client_for(exam, user=None):
    app = FastAPI()
    app.include_router(hr_recording.router)
    app.dependency_overrides[get_db] = lambda: exam.db
    app.dependency_overrides[get_current_user] = lambda: user or exam.user
    app.dependency_overrides[require_student] = lambda: user or exam.user
    return TestClient(app)


def test_pending_history_is_recoverable_without_releasing_scores(exam):
    exam.recording.submission_json = body(exam).model_dump_json()
    exam.interview.evaluation_json = json.dumps({"dimensions": {"behavioral": 95}})
    exam.db.commit()
    history = mock_interview.mock_interview_history(exam.user, exam.db)
    assert history[0]["id"] == exam.interview.id
    assert history[0]["analysis_status"] == "pending"
    assert history[0]["overall_score"] is None
    assert history[0]["dimensions"] == {}
    assert exams.saved_interview_result(exam.interview.id, exam.user, exam.db)["result"] is None
    outsider = User(id="outsider", email="outsider@example.com", username="outsider", hashed_password="hash", role=UserRole.student)
    exam.db.add_all([outsider, StudentProfile(user_id=outsider.id, full_name="Other student")])
    exam.db.commit()
    assert mock_interview.mock_interview_history(outsider, exam.db) == []
    with pytest.raises(HTTPException) as error:
        exams.saved_interview_result(exam.interview.id, outsider, exam.db)
    assert error.value.status_code == 404


def test_recording_access_is_owner_or_same_institution_reviewer(exam):
    assert hr_video.owned_recording(exam.db, exam.user, "interview")[0].id == "recording"
    for role, org, reviewer in [(UserRole.student, "org", True), (UserRole.recruiter, "org", True),
                                (UserRole.platform_admin, "org", True), (UserRole.institution_admin, "other", True),
                                (UserRole.institution_admin, "org", False), (UserRole.institution_admin, None, True)]:
        with pytest.raises(HTTPException) as error:
            hr_video.owned_recording(exam.db, SimpleNamespace(id="other", role=role, organization_id=org), "interview", reviewer=reviewer)
        assert error.value.status_code == 404
    reviewer = SimpleNamespace(id="admin", role=UserRole.institution_admin, organization_id="org")
    assert hr_video.owned_recording(exam.db, reviewer, "interview", reviewer=True)[0].id == "recording"


def test_clock_starts_after_preflight_and_cannot_reset(exam):
    exam.clock.now += timedelta(minutes=15)
    first = hr_video.start_exam(exam.db, exam.recording, exam.interview)
    assert first["exam_deadline_at"] == (exam.clock.now + timedelta(minutes=116)).isoformat() + "Z"
    exam.clock.now += timedelta(minutes=5)
    assert hr_video.start_exam(exam.db, exam.recording, exam.interview)["exam_started_at"] == first["exam_started_at"]
    with pytest.raises(HTTPException):
        hr_video.begin_recording(exam.db, exam.recording, exam.interview, "video/webm", False)
    state = hr_video.begin_recording(exam.db, exam.recording, exam.interview, "video/webm", True)
    assert state["question_deadline_at"] == (exam.clock.now + timedelta(seconds=150)).isoformat() + "Z"
    exam.clock.now += timedelta(seconds=5)
    assert hr_video.begin_recording(exam.db, exam.recording, exam.interview, "video/webm", True)["started_at"] == state["started_at"]


def test_question_timing_and_replay_cannot_extend_answer(exam):
    begin(exam)
    exam.clock.now += timedelta(seconds=170)
    first = hr_video.advance_question(exam.db, exam.recording, exam.interview, 1)
    assert first["segments"] == [{"question_id": 1, "start": 0, "end": 150}, {"question_id": 2, "start": 170, "end": None}]
    exam.clock.now += timedelta(seconds=10)
    assert hr_video.advance_question(exam.db, exam.recording, exam.interview, 1)["segments"] == first["segments"]
    with pytest.raises(HTTPException):
        hr_video.advance_question(exam.db, exam.recording, exam.interview, 4)
    exam.clock.now += timedelta(seconds=500)
    state = hr_video.advance_question(exam.db, exam.recording, exam.interview, 2)
    assert state["status"] == "recorded"
    assert state["segments"][-1]["end"] == 320


def test_upload_bounds_and_immutable_idempotent_chunks(exam):
    begin(exam)
    for sequence, data, code in [(-1, b"x", 413), (hr_video.MAX_CHUNKS, b"x", 413), (0, b"", 413),
                                  (0, b"x" * (hr_video.CHUNK_BYTES + 1), 413), (0, b"not-video", 415),
                                  (1, b"x", 409)]:
        with pytest.raises(HTTPException) as error:
            hr_video.save_chunk(exam.db, exam.recording, exam.interview, sequence, data)
        assert error.value.status_code == code
    data = b"\x1a\x45\xdf\xa3video"
    hr_video.save_chunk(exam.db, exam.recording, exam.interview, 0, data)
    assert hr_video.save_chunk(exam.db, exam.recording, exam.interview, 0, data)["saved"]
    assert exam.recording.chunk_count == 1
    with pytest.raises(HTTPException) as error:
        hr_video.save_chunk(exam.db, exam.recording, exam.interview, 0, data + b"changed")
    assert error.value.status_code == 409
    hr_video.seal_recording(exam.db, exam.recording, 1)
    assert hr_video.save_chunk(exam.db, exam.recording, exam.interview, 0, data)["saved"]
    with pytest.raises(HTTPException):
        hr_video.save_chunk(exam.db, exam.recording, exam.interview, 1, b"new")
    with pytest.raises(HTTPException):
        hr_video.seal_recording(exam.db, exam.recording, 2)


def test_upload_stream_is_bounded_and_unauthorized_owner_is_rejected(exam):
    begin(exam)
    response = client_for(exam).put("/mock-interview/interview/hr/chunks/0", content=b"x" * (hr_video.CHUNK_BYTES + 1))
    assert response.status_code == 413
    assert exam.db.query(HRVideoChunk).count() == 0
    stranger = SimpleNamespace(id="stranger", role=UserRole.student, organization_id="org")
    response = client_for(exam, stranger).put("/mock-interview/interview/hr/chunks/0", content=b"anything")
    assert response.status_code == 404


def test_private_playback_uses_bounded_ranges_and_enforces_expiry(exam):
    begin(exam)
    data = b"\x1a\x45\xdf\xa3" + b"v" * (hr_video.CHUNK_BYTES - 4)
    for sequence in range(5):
        hr_video.save_chunk(exam.db, exam.recording, exam.interview, sequence, data)
    hr_video.seal_recording(exam.db, exam.recording, 5)
    client = client_for(exam)
    url = "/mock-interview/interview/hr/recording"
    response = client.get(url)
    assert response.status_code == 206
    assert len(response.content) == hr_video.PLAYBACK_BYTES
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-range"] == f"bytes 0-{hr_video.PLAYBACK_BYTES-1}/{len(data)*5}"
    tail = client.get(url, headers={"Range": f"bytes={hr_video.PLAYBACK_BYTES}-"})
    assert tail.status_code == 206 and tail.content == data
    assert client.get(url, headers={"Range": "bytes=-7"}).content == b"v" * 7
    for bad in ["bytes=1-0", "bytes=999999999-", "bytes=0-5,7-9", "bytes=-0", "invalid"]:
        assert client.get(url, headers={"Range": bad}).status_code == 416
    stranger = SimpleNamespace(id="stranger", role=UserRole.student, organization_id="org")
    assert client_for(exam, stranger).get(url).status_code == 404
    exam.clock.now = exam.recording.expires_at
    assert client.get(url).status_code == 410


def test_lease_is_atomic_and_stale_worker_cannot_clear_new_lease(exam):
    lease = hr_video.acquire_lease(exam.db, exam.recording, "analysis_lease_until", minutes=5)
    with Session(exam.engine) as other:
        row = other.get(HRRecording, "recording")
        with pytest.raises(HTTPException) as error:
            hr_video.acquire_lease(other, row, "analysis_lease_until", minutes=5)
        assert error.value.status_code == 409
    hr_video.release_lease(exam.db, exam.recording, "analysis_lease_until", lease - timedelta(seconds=1))
    exam.db.refresh(exam.recording)
    assert exam.recording.analysis_lease_until == lease
    exam.clock.now += timedelta(minutes=6)
    fresh = hr_video.acquire_lease(exam.db, exam.recording, "analysis_lease_until", minutes=5)
    hr_video.release_lease(exam.db, exam.recording, "analysis_lease_until", lease)
    exam.db.refresh(exam.recording)
    assert exam.recording.analysis_lease_until == fresh


@pytest.mark.parametrize("mutation", ["outside_segment", "duplicate_question", "unusable_audio", "unusable_video", "invented_answer"])
def test_video_analysis_requires_valid_question_evidence(exam, mutation):
    seal(exam)
    value = analysis(exam)
    if mutation == "outside_segment":
        value["answers"][0]["evidence"][0]["at_seconds"] = 55
    elif mutation == "duplicate_question":
        value["answers"][0]["question_id"] = 2
    elif mutation == "unusable_audio":
        value["audio_usable"] = False
    elif mutation == "unusable_video":
        value["video_usable"] = False
    else:
        exam.recording.segments_json = json.dumps(json.loads(exam.recording.segments_json)[:3])
        value["answers"][3]["evidence"][0]["at_seconds"] = 30
    with pytest.raises(RuntimeError):
        hr_video._validate_analysis(hr_video.VideoAnalysis.model_validate(value), exam.recording, exam.questions)


def test_no_speech_cannot_receive_fluency_or_correctness_points(exam):
    seal(exam)
    value = analysis(exam)
    value["answers"][0]["transcript"] = ""
    result = hr_video._validate_analysis(hr_video.VideoAnalysis.model_validate(value), exam.recording, exam.questions)
    assert result["answers"][0]["answer_correctness"] == result["answers"][0]["english_fluency"] == 0


def test_failed_provider_preserves_submission_and_retry_uses_original_answers(exam, monkeypatch):
    seal(exam)
    original = body(exam)
    calls = []

    def fail(*args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(hr_video, "_analyze_video", fail)
    with pytest.raises(HTTPException) as error:
        exams.evaluate_mock_interview_v2(original, exam.user, exam.db)
    assert error.value.status_code == 503
    exam.db.refresh(exam.recording)
    assert json.loads(exam.recording.submission_json) == original.model_dump()
    assert json.loads(exam.interview.answers_json) == [answer.model_dump() for answer in original.answers]
    assert exam.recording.analysis_lease_until is None and exam.recording.evaluation_lease_until is None
    assert exams.saved_interview_result("interview", exam.user, exam.db)["result"] is None

    def analyze(*args):
        calls.append(True)
        return analysis(exam)

    monkeypatch.setattr(hr_video, "_analyze_video", analyze)
    monkeypatch.setattr(exams, "_evaluate_subjective_with_ai", lambda **kwargs: ([], {}))
    result = exams.evaluate_mock_interview_v2(body(exam, "attempted answer replacement"), exam.user, exam.db)
    assert result["analysis_status"] == "complete"
    assert all(item["answer"] == "[HR video response recorded]" for item in json.loads(exam.interview.answers_json))
    assert exams.retry_saved_interview("interview", exam.user, exam.db)["overall_score"] == result["overall_score"]
    assert len(calls) == 1
    assert exams.saved_interview_result("interview", exam.user, exam.db)["status"] == "complete"


def test_partial_non_video_analysis_never_releases_hr_or_other_scores(exam, monkeypatch):
    seal(exam)
    question = {"question_id": 5, "question": "How would you validate a SQL query before release?", "section": "technical",
                "category": "technical", "difficulty": "medium", "answer_type": "text"}
    exam.interview.questions_json = json.dumps([*exam.questions, question])
    exam.db.commit()
    monkeypatch.setattr(hr_video, "_analyze_video", lambda *args: analysis(exam))
    monkeypatch.setattr(exams, "_obvious_answer_failure", lambda *args: None)
    monkeypatch.setattr(exams, "_evaluate_subjective_with_ai", lambda **kwargs: ([], {}))
    with pytest.raises(HTTPException) as error:
        exams.evaluate_mock_interview_v2(body(exam, "I would validate the SQL query using expected results and edge cases."), exam.user, exam.db)
    assert error.value.status_code == 503
    assert exam.interview.overall_score is None
    assert json.loads(exam.interview.evaluation_json) == {"analysis_status": "pending"}
    assert exams.saved_interview_result("interview", exam.user, exam.db)["result"] is None


def test_unstarted_hr_is_unanswered_and_cannot_be_recorded_after_submission(exam, monkeypatch):
    hr_video.start_exam(exam.db, exam.recording, exam.interview)
    monkeypatch.setattr(exams, "_evaluate_subjective_with_ai", lambda **kwargs: ([], {}))
    result = exams.evaluate_mock_interview_v2(body(exam), exam.user, exam.db)
    assert result["overall_score"] == 0
    assert all(item["grading_method"] == "system" for item in result["evaluations"])
    with pytest.raises(HTTPException):
        hr_video.begin_recording(exam.db, exam.recording, exam.interview, "video/webm", True)


def test_corrupted_recording_is_not_sent_to_provider(exam, monkeypatch):
    seal(exam)
    chunk = exam.db.get(HRVideoChunk, ("recording", 0))
    chunk.sha256 = hashlib.sha256(b"different").hexdigest()
    exam.db.commit()
    monkeypatch.setattr(hr_video, "_analyze_video", lambda *args: pytest.fail("corrupt data must not leave storage"))
    with pytest.raises(HTTPException) as error:
        hr_video.analyze_recording(exam.db, exam.recording, exam.interview)
    assert error.value.status_code == 503


def test_processing_retry_reuses_provider_file_and_deletes_after_analysis(exam, monkeypatch):
    from google import genai

    seal(exam)
    counts = {"uploads": 0, "deletes": 0, "generations": 0}
    state = SimpleNamespace(active=False)
    def provider_file():
        return SimpleNamespace(name="files/test-recording", uri="https://example.com/video",
                               state=SimpleNamespace(name="ACTIVE" if state.active else "PROCESSING"))
    def upload(**kwargs):
        counts["uploads"] += 1
        return provider_file()
    def delete(**kwargs):
        counts["deletes"] += 1
    def generate(**kwargs):
        counts["generations"] += 1
        return SimpleNamespace(text=json.dumps(analysis(exam)))
    client = SimpleNamespace(files=SimpleNamespace(upload=upload, get=lambda **kwargs: provider_file(), delete=delete),
                             models=SimpleNamespace(generate_content=generate), close=lambda: None)
    monkeypatch.setattr(genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(hr_video, "_gemini_key", lambda: "unit-test-only")
    monkeypatch.setattr(hr_video, "get_settings", lambda: SimpleNamespace(gemini_model="gemini-test"))
    monkeypatch.setattr(hr_video.time, "sleep", lambda value: None)
    with pytest.raises(HTTPException):
        hr_video.analyze_recording(exam.db, exam.recording, exam.interview)
    assert exam.recording.provider_file_name == "files/test-recording"
    assert counts == {"uploads": 1, "deletes": 0, "generations": 0}
    state.active = True
    assert hr_video.analyze_recording(exam.db, exam.recording, exam.interview)["audio_usable"]
    assert counts == {"uploads": 1, "deletes": 1, "generations": 1}
    assert exam.recording.provider_file_name is None
