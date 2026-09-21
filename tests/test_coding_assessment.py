from __future__ import annotations

from types import SimpleNamespace

from app import coding_assessment


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_public_spec_hides_hidden_cases():
    spec = coding_assessment.CODING_CHALLENGE_BANK[0]
    public = coding_assessment.public_coding_spec(spec)
    assert len(public["sample_tests"]) == 2
    assert public["hidden_test_count"] == 6
    assert "test_cases" not in public
    hidden_inputs = {case["input"] for case in spec["test_cases"] if case["hidden"]}
    serialized = str(public)
    assert all(value not in serialized for value in hidden_inputs)


def test_challenge_selection_returns_requested_distinct_items():
    selected = coding_assessment.choose_coding_challenges(
        seed_value="job-1:Software Engineer",
        previous_questions=[],
        count=2,
    )
    assert len(selected) == 2
    assert selected[0]["key"] != selected[1]["key"]
    assert all(len(item["test_cases"]) == 8 for item in selected)


def test_execute_test_suite_maps_compile_and_test_results_without_network(monkeypatch):
    monkeypatch.setattr(coding_assessment, "_language_id", lambda language: 71)
    monkeypatch.setattr(coding_assessment.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        coding_assessment,
        "get_settings",
        lambda: SimpleNamespace(coding_execution_enabled=True),
    )
    monkeypatch.setattr(
        coding_assessment.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse([{"token": "a"}, {"token": "b"}]),
    )
    monkeypatch.setattr(
        coding_assessment.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "submissions": [
                {
                    "token": "a",
                    "stdout": "YES\n",
                    "stderr": None,
                    "compile_output": None,
                    "status": {"id": 3, "description": "Accepted"},
                    "time": "0.01",
                    "memory": 1000,
                },
                {
                    "token": "b",
                    "stdout": "YES\n",
                    "stderr": None,
                    "compile_output": None,
                    "status": {"id": 3, "description": "Accepted"},
                    "time": "0.01",
                    "memory": 1000,
                },
            ]
        }),
    )
    result = coding_assessment.execute_test_suite(
        source_code="print('YES')",
        language="python",
        test_cases=[
            {"input": "x\n", "expected_output": "YES\n", "hidden": False},
            {"input": "y\n", "expected_output": "NO\n", "hidden": True},
        ],
    )
    assert result["compile_success"] is True
    assert result["passed"] == 1
    assert result["total"] == 2
    assert result["pass_rate"] == 50
    assert result["test_results"][0]["passed"] is True
    assert result["test_results"][1]["passed"] is False


def test_execute_test_suite_reports_compilation_failure(monkeypatch):
    monkeypatch.setattr(coding_assessment, "_language_id", lambda language: 71)
    monkeypatch.setattr(coding_assessment.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        coding_assessment,
        "get_settings",
        lambda: SimpleNamespace(coding_execution_enabled=True),
    )
    monkeypatch.setattr(
        coding_assessment.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse([{"token": "a"}]),
    )
    monkeypatch.setattr(
        coding_assessment.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "submissions": [{
                "token": "a",
                "stdout": "",
                "stderr": "",
                "compile_output": "SyntaxError",
                "status": {"id": 6, "description": "Compilation Error"},
                "time": None,
                "memory": None,
            }]
        }),
    )
    result = coding_assessment.execute_test_suite(
        source_code="bad code",
        language="python",
        test_cases=[{"input": "", "expected_output": "", "hidden": False}],
    )
    assert result["compile_success"] is False
    assert result["passed"] == 0
    assert result["pass_rate"] == 0
    assert "SyntaxError" in result["compile_output"]
