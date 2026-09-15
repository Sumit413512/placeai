from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_production_application_is_monitored() -> None:
    workflow = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
    assert "BASE_URL: https://www.placeai.in" in workflow
    assert '"$BASE_URL/health"' in workflow
    assert "FORM_CONTRACTS" in workflow
    assert "integration-readiness.js" in workflow
    assert "data-access-request-status" in workflow
    assert "/provision-recruiter" in workflow


def test_vercel_main_is_the_authoritative_production_release_branch() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    deployment_enabled = config["git"]["deploymentEnabled"]
    assert deployment_enabled.get("main") is True
    assert deployment_enabled.get("**") is False


def test_vercel_serves_the_complete_ui_instead_of_redirecting_to_render() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    redirects = config.get("redirects") or []
    assert not any(item.get("source") == "/" for item in redirects)

    app_source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
    assert 'release-ux-fixes.js' in app_source
    assert 'legal-links.js' in app_source
    assert '@app.api_route("/privacy"' in app_source
    assert '@app.api_route("/terms"' in app_source
    assert '@app.api_route("/acceptable-use"' in app_source
    assert '@app.get("/robots.txt"' in app_source
    assert '@app.get("/sitemap.xml"' in app_source


def test_ci_generates_commit_specific_integrity_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Generate release integrity evidence" in workflow
    assert "git ls-files -z" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert not (ROOT / "MANIFEST.sha256").exists()
