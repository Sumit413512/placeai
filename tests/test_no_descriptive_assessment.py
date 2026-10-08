from pathlib import Path

from app import answer_recording
from app.routers import mock_interview_v2

ROOT = Path(__file__).resolve().parents[1]


def _issued_blueprint():
    rows = []
    for section, _, count in mock_interview_v2.ASSESSMENT_BLUEPRINT:
        for index in range(count):
            item = {"question": f"{section} {index}", "section": section, "category": section, "difficulty": "medium"}
            if section in mock_interview_v2.OBJECTIVE_ASSESSMENT_SECTIONS:
                item.update(answer_type="mcq", options=["A", "B", "C", "D"], correct_answer="A")
            elif section == "coding":
                item.update(answer_type="code", options=[], correct_answer="", coding_spec={})
            else:
                item.update(answer_type="text", options=[], correct_answer="")
            rows.append(item)
    return rows


def test_standardized_exam_has_no_descriptive_text_response_mode():
    questions = mock_interview_v2._apply_standard_assessment_response_contract(_issued_blueprint())
    assert len(questions) == 50
    assert sum(q["answer_type"] == "mcq" for q in questions) == 36
    assert sum(q["answer_type"] == "code" for q in questions) == 2
    assert sum(q["answer_type"] == "audio" for q in questions) == 8
    assert sum(q["answer_type"] == "video" for q in questions) == 4
    assert not any(q["answer_type"] == "text" for q in questions)
    for q in questions:
        if q["section"] in {"resume", "role", "situational"}:
            assert q["response_mode"] == "audio"
            assert q["narration_enabled"] is True
            assert q["expected_answer_size"] in mock_interview_v2.SPOKEN_ANSWER_SECONDS_BY_SIZE
            assert q["answer_time_seconds"] == mock_interview_v2.SPOKEN_ANSWER_SECONDS_BY_SIZE[q["expected_answer_size"]]
        elif q["section"] == "behavioral":
            assert q["answer_type"] == "video"
            assert q["response_mode"] == "video"
            assert q["narration_enabled"] is True
            assert q["answer_time_seconds"] == mock_interview_v2.hr_video.QUESTION_SECONDS


def test_legacy_full_assessment_resume_is_upgraded_to_private_audio():
    questions = []
    question_id = 1
    for section, count in answer_recording.FULL_ASSESSMENT_SECTION_COUNTS.items():
        for _ in range(count):
            answer_type = "video" if section == "behavioral" else "code" if section == "coding" else "mcq" if section not in {"resume", "role", "situational"} else "text"
            questions.append({"question_id": question_id, "section": section, "answer_type": answer_type})
            question_id += 1
    assert answer_recording.materialize_post_hr_modes(questions) is True
    spoken = [q for q in questions if q["section"] in {"resume", "role", "situational"}]
    assert len(spoken) == 8
    assert all(q["answer_type"] == "audio" and q["response_mode"] == "audio" for q in spoken)


def test_assessment_frontend_has_no_descriptive_answer_textarea_and_fails_closed():
    app_js = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/mock-interview.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "Write a concise, evidence-based response." not in app_js
    assert "Unsupported response mode" in app_js
    assert "response_mode_invalid" in app_js
    assert "kind:'audio'" in app_js
    assert "['resume','role','situational']" in app_js


def test_assessment_audio_compatibility_layer_includes_resume_and_no_written_grading_label():
    app_js = (ROOT / "app/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/assessment-audio-enhancements.js").read_text(encoding="utf-8")
    assert app_js == public_js
    assert "new Set(['resume', 'role', 'situational'])" in app_js
    assert "Resume & Project Defence" in app_js
    assert "next.answer_type = 'audio'" in app_js
    assert "written, spoken" not in app_js


def test_spoken_answer_windows_scale_with_question_size_and_server_floors():
    questions = _issued_blueprint()
    role = [q for q in questions if q["section"] == "role"]
    resume = [q for q in questions if q["section"] == "resume"]
    situational = [q for q in questions if q["section"] == "situational"]

    role[0].update(difficulty="easy", question="Name one capability you would prioritise.", expected_answer_size="short")
    role[1].update(difficulty="hard", question="Explain the capability, evidence, trade-off and validation plan.", expected_answer_size="medium")
    resume[0].update(difficulty="easy", question="Name one relevant project.", expected_answer_size="short")
    situational[0].update(difficulty="medium", question="Walk through what you would do, how you would communicate risk, and how you would verify the outcome.", expected_answer_size="short")

    normalized = mock_interview_v2._apply_standard_assessment_response_contract(questions)
    by_question = {q["question"]: q for q in normalized}

    assert by_question["Name one capability you would prioritise."]["expected_answer_size"] == "short"
    assert by_question["Name one capability you would prioritise."]["answer_time_seconds"] == 60
    assert by_question["Explain the capability, evidence, trade-off and validation plan."]["expected_answer_size"] == "long"
    assert by_question["Explain the capability, evidence, trade-off and validation plan."]["answer_time_seconds"] == 120
    assert by_question["Name one relevant project."]["expected_answer_size"] == "medium"
    assert by_question["Name one relevant project."]["answer_time_seconds"] == 90
    assert by_question["Walk through what you would do, how you would communicate risk, and how you would verify the outcome."]["expected_answer_size"] == "long"
    assert by_question["Walk through what you would do, how you would communicate risk, and how you would verify the outcome."]["answer_time_seconds"] == 120


def test_client_spoken_answer_timer_uses_server_question_window():
    app_js = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    assert "Number(q.answer_time_seconds)||150" in app_js
    assert "Math.max(45,Math.min(150" in app_js
