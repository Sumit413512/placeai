import json
from types import SimpleNamespace

from app import trial_demo_access


def _questions(*, audio=0, video=4, total=50):
    rows = []
    for index in range(total):
        row = {"question_id": index + 1, "answer_type": "mcq"}
        if index < audio:
            row.update({"answer_type": "text", "response_mode": "audio"})
        elif index < audio + video:
            row["answer_type"] = "video"
        rows.append(row)
    return rows


def _interview(*, questions, score=None):
    return SimpleNamespace(questions_json=json.dumps(questions), overall_score=score)


def test_legacy_demo_without_private_spoken_modes_does_not_consume_current_attempt():
    row = _interview(questions=_questions(audio=0, video=4), score=None)
    assert trial_demo_access._counts_as_trial_attempt(row) is False


def test_current_standardized_demo_consumes_attempt_when_started():
    row = _interview(questions=_questions(audio=8, video=4), score=None)
    assert trial_demo_access._counts_as_trial_attempt(row) is True


def test_completed_historical_attempt_still_consumes_attempt():
    row = _interview(questions=_questions(audio=0, video=4), score=72)
    assert trial_demo_access._counts_as_trial_attempt(row) is True


def test_malformed_or_nonstandard_question_set_does_not_consume_demo_grant():
    malformed = SimpleNamespace(questions_json="not-json", overall_score=None)
    short = _interview(questions=_questions(audio=8, video=4, total=49), score=None)
    assert trial_demo_access._counts_as_trial_attempt(malformed) is False
    assert trial_demo_access._counts_as_trial_attempt(short) is False
