from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.app import app
from app.routers.ai_experience import _repair_pdf_text, _merge_profile_skills
from app.routers.mock_interview_v2 import MockInterviewStartV2, _too_similar


ROOT = Path(__file__).resolve().parents[1]


def _route(path: str, method: str):
    matches = [
        route for route in app.routes
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, f"expected exactly one {method} {path}, got {len(matches)}"
    return matches[0]


def test_user_reported_ai_routes_use_hardened_implementation():
    assert _route("/ai/parse-resume", "POST").endpoint.__module__ == "app.routers.ai_experience"
    assert _route("/ai/generate-summary", "POST").endpoint.__module__ == "app.routers.ai_experience"


def test_user_reported_campus_views_use_graceful_student_workspace_routes():
    assert _route("/enterprise/calendar", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _route("/enterprise/announcements", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _route("/enterprise/custom-fields", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _route("/enterprise/student-campus-status", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"


def test_resume_text_repairs_common_pdf_artifacts_and_merges_skills():
    repaired = _repair_pdf_text("P y t h o n\nsoft-\nware\u00a0engineering\nReact.js")
    assert "Python" in repaired
    assert "software engineering" in repaired
    skills = _merge_profile_skills(["Python", "Docker"], ["python", "React.js", "SQL"])
    assert skills == ["Python", "Docker", "React.js", "SQL"]


def test_mock_interview_supports_longer_role_specific_rounds():
    config = MockInterviewStartV2(
        job_id="job-1", focus="technical", question_count=15, difficulty="hard", mode="practice"
    )
    assert config.question_count == 15
    assert config.difficulty == "hard"
    with pytest.raises(ValidationError):
        MockInterviewStartV2(job_id="job-1", question_count=16)


def test_mock_interview_similarity_guard_rejects_repeat_and_paraphrase():
    prior = ["Explain how you would design a REST API for a placement platform"]
    assert _too_similar("Explain how you would design a REST API for a placement platform", prior)
    assert not _too_similar("How would you investigate a memory leak in a Python service?", prior)


def test_mock_interview_v2_owns_start_and_evaluation_routes():
    assert _route("/mock-interview/start", "POST").endpoint.__module__ == "app.routers.mock_interview_v2"
    assert _route("/mock-interview/evaluate", "POST").endpoint.__module__ == "app.routers.mock_interview_v2"


def test_frontend_exposes_extended_interview_and_runtime_performance_controls():
    html = (ROOT / "app" / "templates" / "mock-interview.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "workspace-runtime.js").read_text(encoding="utf-8")
    proxy = (ROOT / "render_proxy.py").read_text(encoding="utf-8")
    assert 'value="15"' in html
    assert 'name="difficulty"' in html
    assert 'id="weak-topic-list"' in html
    assert 'id="practice-plan-list"' in html
    assert "CACHEABLE" in script and "inflight" in script and "allSkills" in script
    assert "max_keepalive_connections" in proxy
