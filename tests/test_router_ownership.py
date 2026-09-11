from pathlib import Path

from app.app import app


def test_canonical_router_ownership_has_no_bootstrap_shadow_filters():
    source = Path("app/app.py").read_text()
    assert "_RETIRED_AI_PATHS" not in source
    assert "_HARDENED_INSTITUTION_PATHS" not in source
    assert 'hardening = _import_router("hardening")' not in source
    assert not Path("app/routers/hardening.py").exists()


def test_canonical_routes_keep_hardened_and_compatibility_owners():
    schema = app.openapi()["paths"]
    assert "rank_candidates" in schema["/ai/rank-candidates/{job_id}"]["post"]["operationId"]
    assert "dashboard" in schema["/institutions/dashboard"]["get"]["operationId"]
    assert "approve_job" in schema["/institutions/jobs/{job_id}/approval"]["patch"]["operationId"]
    assert schema["/ai/interview/questions"]["post"]["deprecated"] is True
    assert schema["/ai/interview/evaluate"]["post"]["deprecated"] is True
    assert "completed_interview_history" in schema["/ai/interviews"]["get"]["operationId"]
