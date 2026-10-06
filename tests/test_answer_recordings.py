import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_hr_video import exam  # noqa: F401
from app import answer_recording, hr_video
from app.database import Base
from app.models import AnswerRecording, AnswerRecordingChunk


@pytest.fixture
def spoken(exam, monkeypatch):
    Base.metadata.create_all(exam.engine, tables=[AnswerRecording.__table__, AnswerRecordingChunk.__table__])
    monkeypatch.setattr(answer_recording, "utcnow", lambda: exam.clock.now)
    questions = exam.questions[:2]
    questions[0].update(answer_type="text", response_mode="audio")
    questions[1].update(response_mode="video")
    exam.interview.questions_json = json.dumps(questions)
    exam.db.commit()
    hr_video.start_exam(exam.db, exam.recording, exam.interview)
    return exam


def capture(exam, qid, mime):
    answer_recording.begin(exam.db, exam.user, "interview", qid, mime, True)
    root, interview, _, row = answer_recording.owned(exam.db, exam.user, "interview", qid, lock=True)
    data = b"\x1a\x45\xdf\xa3synthetic-answer-" + bytes([qid])
    answer_recording.upload(exam.db, root, interview, row, 0, data)
    return row, data


def test_separate_answers_are_owned_immutable_and_cannot_overlap(spoken):
    row, data = capture(spoken, 1, "audio/webm")
    with pytest.raises(HTTPException) as error:
        answer_recording.begin(spoken.db, spoken.user, "interview", 2, "video/webm", True)
    assert error.value.status_code == 409
    hr_video.seal_recording(spoken.db, row, 1)
    other, other_data = capture(spoken, 2, "video/webm")
    assert row.id != other.id
    assert spoken.db.get(AnswerRecordingChunk, (row.id, 0)).data == data
    assert spoken.db.get(AnswerRecordingChunk, (other.id, 0)).data == other_data
    with pytest.raises(HTTPException) as error:
        answer_recording.owned(spoken.db, SimpleNamespace(id="intruder"), "interview", 1)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        answer_recording.upload(spoken.db, spoken.recording, spoken.interview, row, 0, data + b"changed")
    assert error.value.status_code == 409


def test_text_cannot_replace_a_required_recording(spoken):
    questions = json.loads(spoken.interview.questions_json)
    submitted = {qid: SimpleNamespace(answer="typed text") for qid in (1, 2)}
    with pytest.raises(HTTPException) as error:
        answer_recording.sealed_answers(spoken.db, spoken.interview, questions, submitted)
    assert error.value.status_code == 409
    submitted = {qid: SimpleNamespace(answer="[No response submitted]") for qid in (1, 2)}
    assert answer_recording.analyze(spoken.db, spoken.interview, questions, submitted) == {}


def test_audio_can_be_assessed_without_visual_evidence(spoken):
    from test_hr_video import analysis
    row, _ = capture(spoken, 1, "audio/webm")
    from datetime import timedelta
    spoken.clock.now += timedelta(seconds=10)
    hr_video.seal_recording(spoken.db, row, 1)
    value = analysis(spoken)
    value["video_usable"] = False
    value["answers"] = value["answers"][:1]
    result = hr_video._validate_analysis(hr_video.VideoAnalysis.model_validate(value), row,
                                        spoken.questions[:1], audio_only=True)
    assert result["answers"][0]["answer_correctness"] == 80
    assert result["video_usable"] is False
    value["audio_usable"] = False
    result = hr_video._validate_analysis(hr_video.VideoAnalysis.model_validate(value), row,
                                        spoken.questions[:1], audio_only=True)
    assert result["answers"][0]["transcript"] == ""
    assert result["answers"][0]["answer_correctness"] == 0


def test_empty_recording_seals_as_no_response_without_provider_call(spoken):
    from app.routers.answer_recordings import Submit, submit
    answer_recording.begin(spoken.db, spoken.user, "interview", 1, "audio/webm", True)
    assert submit("interview", 1, Submit(chunks=0), spoken.user, spoken.db)["status"] == "submitted"
    questions = json.loads(spoken.interview.questions_json)
    submitted = {qid: SimpleNamespace(answer="[No response submitted]") for qid in (1, 2)}
    assert answer_recording.analyze(spoken.db, spoken.interview, questions, submitted) == {}


def test_recovery_reuses_completed_question_analysis(spoken, monkeypatch):
    rows = [capture(spoken, 1, "audio/webm")[0]]
    hr_video.seal_recording(spoken.db, rows[0], 1)
    rows.append(capture(spoken, 2, "video/webm")[0])
    hr_video.seal_recording(spoken.db, rows[1], 1)
    calls = []
    failing = {"value": True}
    class QuotaError(Exception):
        code = 429
    def provider(data, row, questions, persist, **kwargs):
        calls.append(row.question_id)
        assert len(questions) == 1 and questions[0]["question_id"] == row.question_id
        assert kwargs.get("audio_only", False) == (row.question_id == 1)
        if row.question_id == 2 and failing["value"]:
            raise QuotaError("secret upstream body")
        return {"summary": "Question feedback", "answers": [{"question_id": row.question_id, "transcript": "A recorded answer"}]}
    monkeypatch.setattr(hr_video, "_analyze_video", provider)
    questions = json.loads(spoken.interview.questions_json)
    submitted = {qid: SimpleNamespace(answer="[Spoken answer submitted]") for qid in (1, 2)}
    with pytest.raises(HTTPException) as error:
        answer_recording.analyze(spoken.db, spoken.interview, questions, submitted)
    assert error.value.detail["code"] == "VIDEO_PROVIDER_CAPACITY"
    assert "secret" not in str(error.value.detail)
    assert rows[0].analysis_json and not rows[1].analysis_json
    failing["value"] = False
    assert set(answer_recording.analyze(spoken.db, spoken.interview, questions, submitted)) == {1, 2}
    assert calls == [1, 2, 2]
    for row in rows:
        spoken.db.refresh(row)
    assert all(row.analysis_lease_until is None for row in rows)
