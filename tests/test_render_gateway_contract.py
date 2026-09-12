from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_gateway_is_versioned_on_main() -> None:
    source = (ROOT / "render_proxy.py").read_text(encoding="utf-8")
    assert 'X-PlaceAI-Gateway' in source
    assert 'Cache-Control' in source
    assert 'no-store' in source
    assert 'no-cache, must-revalidate' in source
    assert 'release_target' in source
    assert 'UPSTREAM_VALIDATION' in source
    assert 'ASSET_VERSION' in source


def test_render_gateway_diagnostics_never_log_request_values() -> None:
    source = (ROOT / "render_proxy.py").read_text(encoding="utf-8")
    assert 'fields=%s' in source
    assert 'body=%s' not in source
    assert 'password=%s' not in source
