from app import answer_recording
from app.routers import mock_interview_v2


def test_recording_timing_policy_stays_aligned_with_assessment_generation():
    assert answer_recording.SPOKEN_ANSWER_SECONDS_BY_SIZE == mock_interview_v2.SPOKEN_ANSWER_SECONDS_BY_SIZE
    assert answer_recording.SPOKEN_ANSWER_SIZE_ORDER == mock_interview_v2.SPOKEN_ANSWER_SIZE_ORDER
    assert answer_recording.SPOKEN_COMPLEXITY_MARKERS == mock_interview_v2.SPOKEN_COMPLEXITY_MARKERS


def test_recording_uses_persisted_server_answer_window_when_present():
    assert answer_recording._answer_time_seconds({"answer_time_seconds": 60}) == 60
    assert answer_recording._answer_time_seconds({"answer_time_seconds": 90}) == 90
    assert answer_recording._answer_time_seconds({"answer_time_seconds": 120}) == 120


def test_legacy_role_question_recovers_short_window_from_difficulty():
    question = {
        "section": "role",
        "difficulty": "easy",
        "question": "Name one capability you would prioritise.",
    }
    assert answer_recording._legacy_answer_size(question) == "short"
    assert answer_recording._answer_time_seconds(question) == 60


def test_legacy_resume_question_keeps_medium_floor():
    question = {
        "section": "resume",
        "difficulty": "easy",
        "question": "Name one relevant project.",
    }
    assert answer_recording._legacy_answer_size(question) == "medium"
    assert answer_recording._answer_time_seconds(question) == 90


def test_legacy_complex_situational_question_promotes_to_long():
    question = {
        "section": "situational",
        "difficulty": "medium",
        "question": "Walk through what you would do, how you would communicate risk, and how you would verify the outcome.",
    }
    assert answer_recording._legacy_answer_size(question) == "long"
    assert answer_recording._answer_time_seconds(question) == 120


def test_expected_answer_size_remains_a_server_floor_for_legacy_rows():
    question = {
        "section": "role",
        "difficulty": "easy",
        "question": "Name one capability.",
        "expected_answer_size": "long",
    }
    assert answer_recording._legacy_answer_size(question) == "long"
    assert answer_recording._answer_time_seconds(question) == 120
