from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.routers.ai_experience import _merge_profile_skills, _repair_pdf_text, router as ai_experience_router
from app.routers.mock_interview_v2 import MockInterviewStartV2, _too_similar, router as mock_interview_v2_router
from app.routers.student_workspace_v2 import router as student_workspace_v2_router


ROOT = Path(__file__).resolve().parents[1]


def _module_route(router, path: str, method: str):
    matches = [
        route for route in router.routes
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, (path, method, len(matches))
    return matches[0]


def test_replacement_routes_bootstrap_once_in_fresh_application_process():
    expected = {
        "/ai/parse-resume|POST": "app.routers.ai_experience",
        "/ai/generate-summary|POST": "app.routers.ai_experience",
        "/enterprise/calendar|GET": "app.routers.student_workspace_v2",
        "/enterprise/announcements|GET": "app.routers.student_workspace_v2",
        "/enterprise/custom-fields|GET": "app.routers.student_workspace_v2",
        "/enterprise/student-campus-status|GET": "app.routers.student_workspace_v2",
        "/mock-interview/start|POST": "app.routers.mock_interview_v2",
        "/mock-interview/evaluate|POST": "app.routers.mock_interview_v2",
    }
    code = r'''
import json
from app.app import app, _router_import_failures
wanted = {
    "/ai/parse-resume|POST", "/ai/generate-summary|POST",
    "/enterprise/calendar|GET", "/enterprise/announcements|GET",
    "/enterprise/custom-fields|GET", "/enterprise/student-campus-status|GET",
    "/mock-interview/start|POST", "/mock-interview/evaluate|POST",
}
found = {}
for route in app.routes:
    path = getattr(route, "path", "")
    for method in (getattr(route, "methods", set()) or set()):
        key = f"{path}|{method}"
        if key in wanted:
            found.setdefault(key, []).append(route.endpoint.__module__)
print(json.dumps({"found": found, "failures": _router_import_failures}, sort_keys=True))
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["failures"] == {}, payload
    assert set(payload["found"]) == set(expected), payload
    for key, owner in expected.items():
        assert payload["found"][key] == [owner], (key, payload["found"][key])


def test_user_reported_ai_routes_use_hardened_implementation():
    assert _module_route(ai_experience_router, "/ai/parse-resume", "POST").endpoint.__module__ == "app.routers.ai_experience"
    assert _module_route(ai_experience_router, "/ai/generate-summary", "POST").endpoint.__module__ == "app.routers.ai_experience"


def test_user_reported_campus_views_use_graceful_student_workspace_routes():
    assert _module_route(student_workspace_v2_router, "/enterprise/calendar", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _module_route(student_workspace_v2_router, "/enterprise/announcements", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _module_route(student_workspace_v2_router, "/enterprise/custom-fields", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"
    assert _module_route(student_workspace_v2_router, "/enterprise/student-campus-status", "GET").endpoint.__module__ == "app.routers.student_workspace_v2"


def test_resume_text_repairs_common_pdf_artifacts_and_merges_skills():
    repaired = _repair_pdf_text("P y t h o n\nsoft-\nware\u00a0engineering\nReact.js")
    assert "Python" in repaired
    assert "software engineering" in repaired
    skills = _merge_profile_skills(["Python", "Docker"], ["python", "React.js", "SQL"])
    assert skills == ["Python", "Docker", "React.js", "SQL"]


def test_mock_interview_supports_longer_role_specific_rounds_and_legacy_clients():
    config = MockInterviewStartV2(
        job_id="job-1", focus="technical", question_count=15, difficulty="hard", mode="practice"
    )
    assert config.question_count == 15
    assert config.difficulty == "hard"
    assert MockInterviewStartV2(job_id="job-1", question_count=3).question_count == 3
    with pytest.raises(ValidationError):
        MockInterviewStartV2(job_id="job-1", question_count=16)


def test_mock_interview_similarity_guard_rejects_repeat_and_paraphrase():
    prior = ["Explain how you would design a REST API for a placement platform"]
    assert _too_similar("Explain how you would design a REST API for a placement platform", prior)
    assert not _too_similar("How would you investigate a memory leak in a Python service?", prior)


def test_mock_interview_v2_owns_start_and_evaluation_routes():
    assert _module_route(mock_interview_v2_router, "/mock-interview/start", "POST").endpoint.__module__ == "app.routers.mock_interview_v2"
    assert _module_route(mock_interview_v2_router, "/mock-interview/evaluate", "POST").endpoint.__module__ == "app.routers.mock_interview_v2"


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
