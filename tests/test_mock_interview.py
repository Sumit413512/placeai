from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.app import app
from app.routers.mock_interview import MockInterviewStart

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
