from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recovery_gateway_loads_access_compat_before_legacy_release_ux() -> None:
    proxy = (ROOT / "render_proxy.py").read_text(encoding="utf-8")
    compat = '/static/recovery-access-compat.js'
    legacy = '/static/release-ux-fixes.js'

    assert compat in proxy
    assert legacy in proxy
    assert proxy.index(compat) < proxy.index(legacy)
    assert '20260915-access-compat-1' in proxy


def test_recovery_access_compat_uses_atomic_provisioning_endpoint() -> None:
    js = (ROOT / "app/static/recovery-access-compat.js").read_text(encoding="utf-8")

    assert '/platform/access-requests/${encodeURIComponent(requestId)}/provision-recruiter' in js
    assert "method: 'POST'" in js
    assert "stopImmediatePropagation()" in js
    assert "document.addEventListener('click'" in js
    assert "}, true);" in js

    # The recovery shim must never reintroduce the obsolete partial-provisioning flow.
    assert "/platform/recruiters" not in js
    assert "/auth/forgot-password" not in js
    assert "method: 'PATCH'" not in js


def test_recovery_access_compat_keeps_provisioned_status_system_managed() -> None:
    js = (ROOT / "app/static/recovery-access-compat.js").read_text(encoding="utf-8")

    assert "option.value === 'provisioned'" in js
    assert "provisionedOptions.forEach(option => option.remove())" in js
    assert "select.disabled = true" in js
    assert "Provisioned status is system-managed" in js
