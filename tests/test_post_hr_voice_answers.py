import json
from pathlib import Path
from types import SimpleNamespace

from app import answer_recording

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


def test_assessment_audio_frontend_policy_is_scoped_and_mirrored():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "new Set(['role', 'situational'])" in app_js
    assert "narration_enabled: true" in app_js
    assert "next.response_mode = 'audio'" in app_js
    assert "spokenRecorderBusy()" in app_js
    assert "Read question aloud" in app_js
    assert "automaticSpokenQuestion" in app_js
    assert "section === 'behavioral'" not in app_js


def test_mock_interview_loads_assessment_audio_enhancement_in_both_static_trees():
    app_loader = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")
    public_loader = (ROOT / "public/static/api-errors.js").read_text(encoding="utf-8")
    assert app_loader == public_loader
    assert "/static/assessment-audio-enhancements.js?v=20261007-voice1" in app_loader
