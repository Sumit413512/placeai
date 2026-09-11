from pathlib import Path

from app.app import app
from app.routers.enterprise import router as enterprise_router


def test_canonical_router_ownership_has_no_bootstrap_shadow_filters():
    source = Path("app/app.py").read_text()
    assert "_RETIRED_AI_PATHS" not in source
    assert "_HARDENED_INSTITUTION_PATHS" not in source
    assert 'hardening = _import_router("hardening")' not in source
    assert not Path("app/routers/hardening.py").exists()
    assert "_retired_enterprise_route" not in source
    assert 'report_export_safe = _import_router("report_export_safe")' not in source
    assert 'hardening2 = _import_router("hardening2")' not in source
    assert not Path("app/routers/report_export_safe.py").exists()
    assert not Path("app/routers/hardening2.py").exists()


def test_canonical_routes_keep_hardened_and_compatibility_owners():
    schema = app.openapi()["paths"]
    assert "rank_candidates" in schema["/ai/rank-candidates/{job_id}"]["post"]["operationId"]
    assert "dashboard" in schema["/institutions/dashboard"]["get"]["operationId"]
    assert "approve_job" in schema["/institutions/jobs/{job_id}/approval"]["patch"]["operationId"]
    assert schema["/ai/interview/questions"]["post"]["deprecated"] is True
    assert schema["/ai/interview/evaluate"]["post"]["deprecated"] is True
    assert "completed_interview_history" in schema["/ai/interviews"]["get"]["operationId"]


def test_enterprise_paths_have_single_canonical_owner():
    expected_local = [
        ("/announcements", "GET"),
        ("/announcements", "POST"),
        ("/drives/{drive_id}/pipeline/default", "POST"),
        ("/drives/{drive_id}/pipeline", "POST"),
        ("/offers/{offer_id}", "PATCH"),
        ("/company-verification/authorization-letter", "POST"),
        ("/offers/{offer_id}/letter", "POST"),
        ("/offers/{offer_id}/letter", "GET"),
        ("/reports/{kind}.{fmt}", "GET"),
    ]
    for path, method in expected_local:
        matches = [
            route
            for route in enterprise_router.routes
            if getattr(route, "path", None) == path
            and method in (getattr(route, "methods", set()) or set())
        ]
        assert len(matches) == 1, (path, method, [getattr(route, "name", None) for route in matches])

    schema = app.openapi()["paths"]
    assert "update_offer" in schema["/enterprise/offers/{offer_id}"]["patch"]["operationId"]
    assert "export_report" in schema["/enterprise/reports/{kind}.{fmt}"]["get"]["operationId"]
    assert "/enterprise/announcements" in schema
    assert "get" in schema["/enterprise/announcements"]
    assert "post" in schema["/enterprise/announcements"]
