from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_platform_access_requests_have_one_frontend_owner():
    """The core workspace owns authenticated Platform Admin access-request loading.

    The access portal is intentionally limited to sign-in, signup, and public access-request
    entry. It must not rotate refresh tokens or intercept the authenticated Access requests
    navigation, because refresh tokens are single-use and the core API client already owns
    refresh/retry behavior.
    """
    portal = (ROOT / "app" / "static" / "access-portal.js").read_text(encoding="utf-8")
    public_portal = (ROOT / "public" / "static" / "access-portal.js").read_text(encoding="utf-8")
    core = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    public_core = (ROOT / "public" / "static" / "app-core.js").read_text(encoding="utf-8")

    assert portal == public_portal
    assert core == public_core

    assert "view === 'leads'" in core
    assert "const rows = await api('/platform/access-requests');" in core
    assert "data-platform-access-status" in core
    assert "platform-provision-recruiter" in core
    assert "api(\`/platform/access-requests/\${encodeURIComponent(id)}\`" in core

    stale_duplicate_markers = (
        "async function platformToken",
        "renderPlatformAccessRequests",
        "data-access-request-status",
        "fetch('/platform/access-requests'",
    )
    for marker in stale_duplicate_markers:
        assert marker not in portal, marker


def test_platform_access_requests_backend_remains_admin_protected():
    source = (ROOT / "app" / "routers" / "access.py").read_text(encoding="utf-8")
    assert '@router.get("/platform/access-requests")' in source
    assert "current_user: User = Depends(require_platform_admin)" in source
