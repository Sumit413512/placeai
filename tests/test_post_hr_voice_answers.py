import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import answer_recording, assessment_queue

ROOT = Path(__file__).resolve().parents[1]


def test_post_hr_sections_use_audio_without_changing_resume_or_legacy_hr():
    assert answer_recording.response_mode({"section": "role", "answer_type": "text"}) == "audio"
    assert answer_recording.response_mode({"section": "situational", "answer_type": "text"}) == "audio"
    assert answer_recording.response_mode({"section": "resume", "answer_type": "text"}) is None
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


def test_queue_enforces_legacy_post_hr_audio_before_admission(monkeypatch):
    interview = SimpleNamespace(
        questions_json=json.dumps([
            {"question_id": 1, "section": "resume", "answer_type": "text"},
            {"question_id": 2, "section": "behavioral", "answer_type": "video"},
            {"question_id": 3, "section": "role", "answer_type": "text"},
            {"question_id": 4, "section": "situational", "answer_type": "text"},
        ])
    )
    body = SimpleNamespace(answers=[
        SimpleNamespace(question_id=1, answer="typed resume answer"),
        SimpleNamespace(question_id=2, answer="[Spoken answer submitted]"),
        SimpleNamespace(question_id=3, answer="text must not bypass audio"),
        SimpleNamespace(question_id=4, answer="text must not bypass audio"),
    ])

    class DB:
        def __init__(self):
            self.flushes = 0

        def flush(self):
            self.flushes += 1

    db = DB()
    calls = []

    def sealed(_db, _interview, issued, submitted):
        calls.append((issued, submitted))
        assert answer_recording.response_mode(issued[2]) == "audio"
        assert answer_recording.response_mode(issued[3]) == "audio"
        assert answer_recording.response_mode(issued[0]) is None
        assert answer_recording.response_mode(issued[1]) is None

    monkeypatch.setattr(answer_recording, "sealed_answers", sealed)
    assessment_queue._enforce_spoken_contract(db, interview, body)

    persisted = json.loads(interview.questions_json)
    assert persisted[0].get("response_mode") is None
    assert persisted[1].get("response_mode") is None
    assert persisted[2]["response_mode"] == "audio"
    assert persisted[2]["narration_enabled"] is True
    assert persisted[3]["response_mode"] == "audio"
    assert persisted[3]["narration_enabled"] is True
    assert db.flushes == 1
    assert len(calls) == 1
    assert set(calls[0][1]) == {1, 2, 3, 4}


def test_queue_spoken_contract_rejects_mismatched_submission_before_worker(monkeypatch):
    interview = SimpleNamespace(
        questions_json=json.dumps([
            {"question_id": 49, "section": "role", "answer_type": "text"},
            {"question_id": 50, "section": "situational", "answer_type": "text"},
        ])
    )
    body = SimpleNamespace(answers=[SimpleNamespace(question_id=49, answer="text")])

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


def test_queue_does_not_convert_resume_or_legacy_hr_to_separate_recordings(monkeypatch):
    interview = SimpleNamespace(
        questions_json=json.dumps([
            {"question_id": 1, "section": "resume", "answer_type": "text"},
            {"question_id": 2, "section": "behavioral", "answer_type": "video"},
        ])
    )
    body = SimpleNamespace(answers=[
        SimpleNamespace(question_id=1, answer="resume"),
        SimpleNamespace(question_id=2, answer="[Spoken answer submitted]"),
    ])

    class DB:
        def flush(self):
            raise AssertionError("No per-question mode should be persisted")

    monkeypatch.setattr(
        answer_recording,
        "sealed_answers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Legacy HR uses its own recorder")),
    )
    assessment_queue._enforce_spoken_contract(DB(), interview, body)
    persisted = json.loads(interview.questions_json)
    assert all(item.get("response_mode") is None for item in persisted)


def test_assessment_audio_frontend_policy_is_scoped_manual_and_mirrored():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "new Set(['role', 'situational'])" in app_js
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


def test_mock_interview_loads_assessment_audio_enhancement_in_both_static_trees():
    app_loader = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")
    public_loader = (ROOT / "public/static/api-errors.js").read_text(encoding="utf-8")
    assert app_loader == public_loader
    assert "/static/assessment-audio-enhancements.js?v=20261007-voice1" in app_loader
