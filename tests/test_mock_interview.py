from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.app import app
from app.routers.mock_interview import MockInterviewStart
from app.routers import mock_interview_v2

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
