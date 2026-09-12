from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_is_authoritative_production_smoke_target() -> None:
    workflow = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
    assert "BASE_URL: https://placeai-recovery.onrender.com" in workflow
    assert "/_recovery/health" in workflow
    assert "FORM_CONTRACTS" in workflow


def test_vercel_git_deployments_are_frozen_while_render_is_release_target() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    deployment_enabled = config["git"]["deploymentEnabled"]
    assert deployment_enabled == {"**": False}


def test_vercel_root_bridges_reset_links_to_render() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    redirects = config.get("redirects") or []
    assert {
        "source": "/",
        "destination": "https://placeai-recovery.onrender.com",
        "permanent": False,
    } in redirects
    workflow = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
    assert "Verify Vercel reset-link bridge preserves token query" in workflow
    assert "VERCEL_CANONICAL_URL: https://placeai-rxpp.vercel.app" in workflow
    assert "VERCEL_MAIN_URL: https://placeai-rxpp-git-main-skj1200519-gmailcoms-projects.vercel.app" in workflow
    assert "reset_token=$token" in workflow


def test_ci_generates_commit_specific_integrity_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Generate release integrity evidence" in workflow
    assert "git ls-files -z" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert not (ROOT / "MANIFEST.sha256").exists()
