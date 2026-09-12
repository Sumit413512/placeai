from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_is_authoritative_production_smoke_target() -> None:
    workflow = (ROOT / ".github" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
    assert "https://placeai-recovery.onrender.com" in workflow
    assert "https://placeai-rxpp.vercel.app" not in workflow
    assert "/_recovery/health" in workflow
    assert "FORM_CONTRACTS" in workflow


def test_vercel_git_deployments_are_frozen_while_render_is_release_target() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    deployment_enabled = config["git"]["deploymentEnabled"]
    assert deployment_enabled == {"**": False}


def test_ci_generates_commit_specific_integrity_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Generate release integrity evidence" in workflow
    assert "git ls-files -z" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert not (ROOT / "MANIFEST.sha256").exists()
