from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW_ID = "institution-access-requests"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_institution_access_view_is_a_first_class_workspace_view_in_both_bundles() -> None:
    app_core = _read("app/static/app.js")
    public_core = _read("public/static/app-core.js")
    app_runtime = _read("app/static/workspace-runtime.js")

    assert app_core == public_core
    assert "['Access','institution-access-requests','Access requests']" in app_core
    assert "if (view === 'institution-access-requests')" in app_core
    assert "data-institution-access-status" in app_core
    assert "loadInstitutionAccessWorkspace();" not in app_runtime


def test_workspace_guard_accepts_institution_access_before_extension_button_mounts() -> None:
    app_guard = _read("app/static/production-polish.js")
    public_guard = _read("public/static/production-polish.js")

    assert app_guard == public_guard
    assert f"const INSTITUTION_ACCESS_VIEW = '{VIEW_ID}';" in app_guard
    assert "if (role === 'institution admin') allowed.add(INSTITUTION_ACCESS_VIEW);" in app_guard
    assert "const active = nav.querySelector('button.active[data-view]');" in app_guard
    assert "const unsupportedLoadingView = loading && !activeValid;" in app_guard


def test_workspace_state_layer_can_persist_and_restore_extension_view() -> None:
    state_layer = _read("app/static/ui-state-fixes.js")

    assert "const SAFE_VIEW = /^[a-z0-9-]{1,48}$/;" in state_layer
    assert "const viewButton = event.target.closest?.('[data-view]');" in state_layer
    assert "if (viewButton?.dataset.view) rememberView(viewButton.dataset.view);" in state_layer
    assert "#app-nav button[data-view]" in state_layer
    assert len(VIEW_ID) <= 48
