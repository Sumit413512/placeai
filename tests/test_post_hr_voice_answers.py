import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import answer_recording, assessment_queue

ROOT = Path(__file__).resolve().parents[1]


def _full_assessment_questions():
    questions = []
    question_id = 1
    for section, count in answer_recording.FULL_ASSESSMENT_SECTION_COUNTS.items():
        if section == "behavioral":
            answer_type = "video"
        elif section == "coding":
            answer_type = "code"
        elif section in {"resume", "role", "situational"}:
            answer_type = "audio"
        else:
            answer_type = "mcq"
        for _ in range(count):
            questions.append({
                "question_id": question_id,
                "question": f"Question {question_id}",
                "section": section,
                "answer_type": answer_type,
            })
            question_id += 1
    return questions


def _answers_for(questions):
    return [
        SimpleNamespace(
            question_id=question["question_id"],
            answer=(
                "text must not bypass required audio"
                if question["section"] in {"resume", "role", "situational"}
                else "submitted answer"
            ),
        )
        for question in questions
    ]


def test_standardized_open_ended_sections_use_audio_without_changing_legacy_hr():
    assert answer_recording.response_mode({"section": "role", "answer_type": "text"}) == "audio"
    assert answer_recording.response_mode({"section": "situational", "answer_type": "text"}) == "audio"
    assert answer_recording.response_mode({"section": "resume", "answer_type": "text"}) == "audio"
    assert answer_recording.response_mode({"section": "behavioral", "answer_type": "video"}) is None
    assert answer_recording.response_mode(
        {"section": "behavioral", "answer_type": "video", "response_mode": "video"}
    ) == "video"


def test_inferred_mode_persists_for_queue_recovery_without_releasing_lock():
    interview = SimpleNamespace(
        questions_json=json.dumps([
            {"question_id": 49, "section": "role", "answer_type": "text"},
            {"question_id": 50, "section": "situational", "answer_type": "text"},
        ])
    )

    class DB:
        def __init__(self):
            self.flushes = 0

        def flush(self):
            self.flushes += 1

        def commit(self):
            raise AssertionError("The inferred-mode helper must not release the locked transaction")

    db = DB()
    answer_recording._persist_inferred_mode(db, interview, 49, "audio")
    items = json.loads(interview.questions_json)
    assert items[0]["response_mode"] == "audio"
    assert items[0]["narration_enabled"] is True
    assert "response_mode" not in items[1]
    assert db.flushes == 1


def test_new_full_assessment_persists_server_authoritative_post_hr_audio():
    target = SimpleNamespace(questions_json=json.dumps(_full_assessment_questions()))
    answer_recording._persist_full_assessment_spoken_policy(None, None, target)
    persisted = json.loads(target.questions_json)

    spoken_audio = [
        item for item in persisted if item["section"] in {"resume", "role", "situational"}
    ]
    assert len(spoken_audio) == 8
    assert all(item["response_mode"] == "audio" for item in spoken_audio)
    assert all(item["answer_type"] == "audio" for item in spoken_audio)
    assert all(item["narration_enabled"] is True for item in spoken_audio)
    assert all(
        item.get("response_mode") == "video"
        for item in persisted
        if item["section"] == "behavioral"
    )
    assert all(
        item["answer_type"] == "video"
        and item["narration_enabled"] is True
        and item["answer_time_seconds"] == answer_recording.hr_video.QUESTION_SECONDS
        for item in persisted
        if item["section"] == "behavioral"
    )


def test_post_hr_materialization_does_not_change_practice_situational_questions():
    practice = [
        {"question_id": 1, "section": "technical", "answer_type": "text"},
        {"question_id": 2, "section": "situational", "answer_type": "text"},
        {"question_id": 3, "section": "behavioral", "answer_type": "text"},
    ]
    assert answer_recording.is_full_assessment_questions(practice) is False
    assert answer_recording.materialize_post_hr_modes(practice) is False
    assert all(item.get("response_mode") is None for item in practice)


def test_queue_enforces_legacy_post_hr_audio_before_admission(monkeypatch):
    questions = _full_assessment_questions()
    interview = SimpleNamespace(questions_json=json.dumps(questions))
    body = SimpleNamespace(answers=_answers_for(questions))

    class DB:
        def __init__(self):
            self.flushes = 0

        def flush(self):
            self.flushes += 1

    db = DB()
    calls = []

    def sealed(_db, _interview, issued, submitted):
        calls.append((issued, submitted))
        spoken = [
            item for item in issued
            if item["section"] in {"resume", "role", "situational"}
        ]
        assert len(spoken) == 8
        assert all(answer_recording.response_mode(item) == "audio" for item in spoken)
        assert all(
            answer_recording.response_mode(item) is None
            for item in issued
            if item["section"] == "behavioral"
        )

    monkeypatch.setattr(answer_recording, "sealed_answers", sealed)
    assessment_queue._enforce_spoken_contract(db, interview, body)

    persisted = json.loads(interview.questions_json)
    spoken = [
        item for item in persisted
        if item["section"] in {"resume", "role", "situational"}
    ]
    assert all(item["response_mode"] == "audio" for item in spoken)
    assert all(item["narration_enabled"] is True for item in spoken)
    assert all(
        item.get("response_mode") is None
        for item in persisted
        if item["section"] == "behavioral"
    )
    assert db.flushes == 1
    assert len(calls) == 1
    assert set(calls[0][1]) == {item["question_id"] for item in persisted}


def test_queue_spoken_contract_rejects_mismatched_submission_before_worker(monkeypatch):
    questions = _full_assessment_questions()
    interview = SimpleNamespace(questions_json=json.dumps(questions))
    body = SimpleNamespace(answers=_answers_for(questions)[:-1])

    class DB:
        def flush(self):
            raise AssertionError("Question metadata must not be flushed for an invalid submission")

    monkeypatch.setattr(
        answer_recording,
        "sealed_answers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Must reject IDs first")),
    )
    with pytest.raises(HTTPException) as exc:
        assessment_queue._enforce_spoken_contract(DB(), interview, body)
    assert exc.value.status_code == 422


def test_queue_does_not_apply_full_assessment_recording_contract_to_practice(monkeypatch):
    practice = [
        {"question_id": 1, "section": "technical", "answer_type": "text"},
        {"question_id": 2, "section": "situational", "answer_type": "text"},
        {"question_id": 3, "section": "behavioral", "answer_type": "text"},
    ]
    interview = SimpleNamespace(questions_json=json.dumps(practice))
    body = SimpleNamespace(answers=_answers_for(practice))

    class DB:
        def flush(self):
            raise AssertionError("Practice questions must not gain recording metadata")

    monkeypatch.setattr(
        answer_recording,
        "sealed_answers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Practice must not require sealed audio")),
    )
    assessment_queue._enforce_spoken_contract(DB(), interview, body)
    persisted = json.loads(interview.questions_json)
    assert all(item.get("response_mode") is None for item in persisted)


def test_assessment_audio_frontend_policy_is_scoped_manual_and_mirrored():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "new Set(['resume', 'role', 'situational'])" in app_js
    assert "next.response_mode = 'audio'" in app_js
    assert "spokenRecorderBusy()" in app_js
    assert "Read question aloud" in app_js
    assert "button.hidden = legacyReader || automaticSpokenQuestion" in app_js
    assert "narration_enabled: true" not in app_js
    assert "section === 'behavioral'" not in app_js


def test_voice_sections_are_labeled_as_spoken_and_manual_narration_cannot_leak():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert "SPOKEN_BLUEPRINT_LABELS" in app_js
    assert "Private spoken answer" in app_js
    assert "meta.textContent?.trim() !== desired" in app_js
    assert "cancelManualReading(button)" in app_js
    assert "currentQuestion !== lastQuestion" in app_js
    assert "document.addEventListener('visibilitychange'" in app_js
    assert "document.querySelector('#spoken-answer-status')" in app_js


def test_report_method_label_includes_written_spoken_and_hr_video_analysis():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert "installGradingMethodLabel()" in app_js
    assert "LEGACY_GRADING_METHOD_LABEL" in app_js
    assert "Answer key + sandbox execution + spoken and HR video analysis" in app_js
    assert "label.textContent?.trim() === LEGACY_GRADING_METHOD_LABEL" in app_js


def test_mock_interview_loads_assessment_audio_enhancement_in_both_static_trees():
    app_loader = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")
    public_loader = (ROOT / "public/static/api-errors.js").read_text(encoding="utf-8")
    assert app_loader == public_loader
    assert "/static/assessment-audio-enhancements.js?v=20261007-voice1" in app_loader
