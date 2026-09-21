from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.app import app
from app.routers.mock_interview import MockInterviewStart
from app.routers import mock_interview_v2
from app.routers.mock_interview_v2 import MockInterviewStartV2

client = TestClient(app)


def test_mock_interview_page_and_api_surface_exist():
    page = client.get("/mock-interview")
    assert page.status_code == 200
    assert "Mock Interview Coach" in page.text
    assert "/static/mock-interview.css" in page.text
    assert "/static/mock-interview.js" in page.text

    paths = client.get("/openapi.json").json()["paths"]
    assert "/mock-interview/jobs" in paths
    assert "/mock-interview/start" in paths
    assert "/mock-interview/evaluate" in paths
    assert "/mock-interview/history" in paths


def test_mock_interview_api_requires_student_authentication():
    response = client.get("/mock-interview/jobs")
    assert response.status_code in {401, 403}


def test_mock_interview_configuration_is_bounded():
    valid = MockInterviewStart(job_id="job-1", focus="hr", question_count=8)
    assert valid.focus == "hr"
    assert valid.question_count == 8

    with pytest.raises(ValidationError):
        MockInterviewStart(job_id="job-1", focus="invalid", question_count=5)
    with pytest.raises(ValidationError):
        MockInterviewStart(job_id="job-1", focus="technical", question_count=9)


def _demo_profile():
    return SimpleNamespace(
        resume=None,
        degree="B.Tech",
        branch="Computer Science",
        skills=["Python", "SQL", "FastAPI"],
        desired_roles=["Software Engineer"],
    )


def _demo_job():
    return SimpleNamespace(
        title="Software Engineer Intern",
        description="Build backend APIs and work with relational databases.",
        required_skills=["Python", "SQL", "FastAPI"],
        preferred_roles=["Software Engineer"],
        experience_required="Fresher",
    )


def test_mock_interview_generation_uses_grounded_fallback_when_ai_fails(monkeypatch):
    def fail_ai(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mock_interview_v2, "_call_interview_ai", fail_ai)
    questions, meta = mock_interview_v2._generate_unique_questions(
        profile=_demo_profile(),
        job=_demo_job(),
        focus="balanced",
        difficulty="mixed",
        count=5,
        previous=[],
    )
    assert len(questions) == 5
    assert [item["question_id"] for item in questions] == [1, 2, 3, 4, 5]
    assert meta["generation_mode"] == "resilient_fallback"
    assert meta["provider"] == "local"
    assert meta["model"] == "role-grounded-v1"
    joined = " ".join(item["question"] for item in questions)
    assert "Software Engineer Intern" in joined
    assert any(skill in joined for skill in ["Python", "SQL", "FastAPI"])


def test_mock_interview_generation_prefers_single_fast_ai_batch(monkeypatch):
    payload = {
        "questions": [
            {"question": "How would you debug a failing Python API request?", "category": "technical", "difficulty": "easy"},
            {"question": "How would you design a SQL query for a reporting requirement?", "category": "technical", "difficulty": "medium"},
            {"question": "Describe a time you incorporated feedback into your work.", "category": "behavioral", "difficulty": "medium"},
            {"question": "How would you clarify an ambiguous backend requirement?", "category": "situational", "difficulty": "hard"},
            {"question": "Why does this Software Engineer Intern role interest you?", "category": "hr", "difficulty": "easy"},
        ]
    }
    calls = []

    def fake_ai(prompt, *, max_output_tokens, fast=False):
        calls.append((max_output_tokens, fast))
        return json.dumps(payload)

    monkeypatch.setattr(mock_interview_v2, "_call_interview_ai", fake_ai)
    monkeypatch.setattr(mock_interview_v2, "current_ai_provider", lambda: "openai")
    monkeypatch.setattr(mock_interview_v2, "current_ai_model", lambda: "gpt-5.6-luna")
    questions, meta = mock_interview_v2._generate_unique_questions(
        profile=_demo_profile(),
        job=_demo_job(),
        focus="balanced",
        difficulty="mixed",
        count=5,
        previous=[],
    )
    assert len(questions) == 5
    assert calls == [(1800, True)]
    assert meta["generation_mode"] == "ai"
    assert meta["provider"] == "openai"
    assert meta["model"] == "gpt-5.6-luna"


def test_resilient_baseline_evaluation_is_conservative_and_explicit():
    job = _demo_job()
    issued = [
        {"question_id": 1, "question": "How would you debug a failing Python API?", "category": "technical", "difficulty": "medium"},
        {"question_id": 2, "question": "Describe how you would validate a SQL change.", "category": "technical", "difficulty": "medium"},
    ]
    submitted = {
        1: mock_interview_v2.MockInterviewAnswerV2(
            question_id=1,
            answer="I would reproduce the Python API issue, inspect logs, isolate the failing input, fix the cause, add tests, and verify the API response and regression cases.",
        ),
        2: mock_interview_v2.MockInterviewAnswerV2(
            question_id=2,
            answer="I would run the SQL in a safe environment, compare expected and actual rows, inspect the query plan if needed, and verify edge cases before release.",
        ),
    }
    result = mock_interview_v2._resilient_baseline_evaluation(
        issued=issued,
        submitted_by_id=submitted,
        job=job,
    )
    assert 0 < result["overall_score"] <= 72
    assert len(result["evaluations"]) == 2
    assert "does not validate technical correctness" in result["overall_feedback"]
    assert "Resilient baseline only" in result["disclaimer"]
    assert all(item["ideal_answer"] == "" for item in result["evaluations"])


def test_full_mock_v2_is_server_standardized_at_fifty_items():
    legacy = MockInterviewStartV2(job_id="job-1")
    assert legacy.mode == "practice"
    assert legacy.question_count == 8

    valid = MockInterviewStartV2(
        job_id="job-1", question_count=50, mode="assessment",
        focus="balanced", difficulty="mixed"
    )
    assert valid.question_count == 50
    assert valid.mode == "assessment"

    with pytest.raises(ValidationError):
        MockInterviewStartV2(job_id="job-1", question_count=15, mode="assessment")
    with pytest.raises(ValidationError):
        MockInterviewStartV2(job_id="job-1", question_count=50, mode="practice")


def test_full_mock_blueprint_totals_fifty_and_has_market_sections():
    blueprint = mock_interview_v2.ASSESSMENT_BLUEPRINT
    assert sum(count for _, _, count in blueprint) == 50
    keys = {key for key, _, _ in blueprint}
    assert keys == {
        "quantitative", "logical", "communication", "technical", "programming",
        "coding", "resume", "behavioral", "role", "situational"
    }


def test_objective_question_scoring_is_exact_and_transparent():
    item = {
        "question_id": 1,
        "question": "What is 2 + 2?",
        "section": "quantitative",
        "category": "quantitative",
        "difficulty": "easy",
        "answer_type": "mcq",
        "options": ["2", "3", "4", "5"],
        "correct_answer": "4",
    }
    correct = mock_interview_v2._objective_evaluation(item, "4")
    wrong = mock_interview_v2._objective_evaluation(item, "5")
    assert correct["score"] == 100
    assert correct["verdict"] == "correct"
    assert correct["grading_method"] == "system"
    assert wrong["score"] == 0
    assert wrong["verdict"] == "incorrect"
    assert wrong["correct_answer"] == "4"


def test_assessment_result_is_withheld_if_any_question_is_not_evaluated():
    issued = [
        {"question_id": 1, "section": "quantitative"},
        {"question_id": 2, "section": "technical"},
    ]
    evaluations = [
        {
            "question_id": 1,
            "section": "quantitative",
            "score": 100,
            "verdict": "correct",
            "grading_method": "system",
        }
    ]
    result = mock_interview_v2._build_assessment_result(
        evaluations=evaluations,
        issued=issued,
        ai_meta={"provider": "test", "model": "test", "batches": 1},
    )
    assert result["analysis_status"] == "incomplete"
    assert result["overall_score"] is None
    assert result["missing_evaluation_question_ids"] == [2]


def test_complete_result_is_derived_from_question_scores_not_ai_overall_impression():
    issued = [
        {"question_id": 1, "section": "quantitative"},
        {"question_id": 2, "section": "technical"},
    ]
    evaluations = [
        {
            "question_id": 1,
            "section": "quantitative",
            "score": 100,
            "verdict": "correct",
            "grading_method": "system",
        },
        {
            "question_id": 2,
            "section": "technical",
            "score": 0,
            "verdict": "incorrect",
            "grading_method": "ai",
        },
    ]
    result = mock_interview_v2._build_assessment_result(
        evaluations=evaluations,
        issued=issued,
        ai_meta={"provider": "test", "model": "test", "batches": 1},
    )
    assert result["analysis_status"] == "complete"
    assert result["raw_assessment_score"] == 50
    assert result["score_summary"]["correct"] == 1
    assert result["score_summary"]["incorrect"] == 1
    assert result["overall_score"] != 82


def test_integrity_models_accept_warning_timeline_and_auto_submit():
    event = mock_interview_v2.MockInterviewIntegrityEventV2(
        event_type="fullscreen_exit",
        detail="Secure full-screen mode was exited.",
        at="2026-09-21T10:00:00Z",
        question=7,
        warning_number=1,
        source="browser",
    )
    payload = mock_interview_v2.MockInterviewEvaluationV2(
        interview_id="interview-1",
        answers=[mock_interview_v2.MockInterviewAnswerV2(question_id=1, answer="Answer")],
        integrity_events=[event],
        integrity_warning_count=4,
        integrity_auto_submitted=True,
        integrity_termination_reason="Warning limit reached",
    )
    assert payload.integrity_warning_count == 4
    assert payload.integrity_auto_submitted is True
    assert payload.integrity_events[0].event_type == "fullscreen_exit"


def test_proctor_and_institution_routes_are_exposed():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/mock-interview/proctor-frame" in paths
    assert "/mock-interview/integrity-event" in paths
    assert "/mock-interview/institution-results" in paths


def test_proctor_frame_requires_student_authentication():
    response = client.post(
        "/mock-interview/proctor-frame",
        json={"interview_id": "missing", "image_data_url": "data:image/jpeg;base64," + ("A" * 200)},
    )
    assert response.status_code in {401, 403}


def test_institution_results_requires_institution_authentication():
    response = client.get("/mock-interview/institution-results")
    assert response.status_code in {401, 403}


def test_full_mock_rejects_malformed_objective_ai_items_and_falls_back_to_valid_mcq(monkeypatch):
    payload = {
        "questions": [
            {
                "question": "Malformed aptitude item with no selectable options",
                "section": "quantitative",
                "category": "quantitative",
                "difficulty": "easy",
                "answer_type": "mcq",
                "options": [],
                "correct_answer": "",
            }
        ]
    }

    def fake_ai(prompt, *, max_output_tokens, fast=False):
        return json.dumps(payload)

    monkeypatch.setattr(mock_interview_v2, "_call_interview_ai", fake_ai)
    questions, _ = mock_interview_v2._generate_unique_questions(
        profile=_demo_profile(),
        job=_demo_job(),
        focus="balanced",
        difficulty="mixed",
        count=50,
        previous=[],
    )

    assert len(questions) == 50
    objective = [
        item for item in questions
        if item["section"] in {"quantitative", "logical", "communication"}
    ]
    assert len(objective) == 22
    assert all(item["answer_type"] == "mcq" for item in objective)
    assert all(len(item["options"]) == 4 for item in objective)
    assert all(item["correct_answer"] in item["options"] for item in objective)


def test_integrity_event_model_accepts_on_device_and_screen_sources():
    on_device = mock_interview_v2.MockInterviewIntegrityEventV2(
        event_type="mobile_phone_detected",
        detail="Phone detected",
        source="on_device_ml",
    )
    screen = mock_interview_v2.MockInterviewIntegrityEventV2(
        event_type="screen_share_stopped",
        detail="Screen sharing stopped",
        source="screen",
    )
    assert on_device.source == "on_device_ml"
    assert screen.source == "screen"


def test_mock_assessment_security_headers_are_scoped_to_assessment_only():
    assessment = client.get("/mock-interview")
    assert assessment.status_code == 200
    permissions = assessment.headers.get("permissions-policy", "")
    csp = assessment.headers.get("content-security-policy", "")
    assert "camera=(self)" in permissions
    assert "microphone=(self)" in permissions
    assert "display-capture=(self)" in permissions
    assert "https://cdn.jsdelivr.net" in csp
    assert "https://storage.googleapis.com" in csp

    home = client.get("/")
    home_permissions = home.headers.get("permissions-policy", "")
    home_csp = home.headers.get("content-security-policy", "")
    assert "camera=()" in home_permissions
    assert "microphone=()" in home_permissions
    assert "https://cdn.jsdelivr.net" not in home_csp
    assert "https://storage.googleapis.com" not in home_csp
