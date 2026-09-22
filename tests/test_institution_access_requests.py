from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.access_models import AccessRequest
from app.app import app
from app.database import SessionLocal
from app.models import Organization, OrganizationType, User, UserRole
from app.routers.institution_access import router as institution_access_router
from app.utils import get_hashed_password

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(email: str, password: str) -> str:
    response = client.post("/auth/login-json", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _route_methods(routes) -> set[tuple[str, str]]:
    return {
        (route.path, method)
        for route in routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_institution_access_routes_are_registered_and_protected() -> None:
    router_routes = _route_methods(institution_access_router.routes)
    assert ("/institutions/access-requests", "GET") in router_routes
    assert ("/institutions/access-requests/{request_id}", "PATCH") in router_routes

    # Verify the externally observable contract instead of relying on FastAPI's
    # mutable/reloaded app.routes registry. A registered protected route must
    # reject an anonymous caller rather than return 404.
    response = client.get("/institutions/access-requests")
    assert response.status_code in {401, 403}, response.text


def test_institution_access_requests_are_tenant_scoped() -> None:
    suffix = uuid.uuid4().hex[:10]
    password = "TenantAccessPass123!"
    db = SessionLocal()
    try:
        org_a = Organization(
            name=f"Tenant Access A {suffix}",
            slug=f"tenant-access-a-{suffix}",
            organization_type=OrganizationType.institution,
            is_active=True,
        )
        org_b = Organization(
            name=f"Tenant Access B {suffix}",
            slug=f"tenant-access-b-{suffix}",
            organization_type=OrganizationType.institution,
            is_active=True,
        )
        db.add_all([org_a, org_b])
        db.flush()

        admin_a = User(
            email=f"tpo-a-{suffix}@example.com",
            username=f"tpoa{suffix}",
            hashed_password=get_hashed_password(password),
            role=UserRole.institution_admin,
            organization_id=org_a.id,
            is_active=True,
            email_verified=True,
        )
        db.add(admin_a)
        db.flush()

        own = AccessRequest(
            requested_role="recruiter",
            full_name="Own Recruiter",
            work_email=f"own-{suffix}@example.com",
            organization_name=org_a.name,
            organization_id=org_a.id,
            status="new",
        )
        other = AccessRequest(
            requested_role="recruiter",
            full_name="Other Recruiter",
            work_email=f"other-{suffix}@example.com",
            organization_name=org_b.name,
            organization_id=org_b.id,
            status="new",
        )
        privileged = AccessRequest(
            requested_role="platform_admin",
            full_name="Platform Request",
            work_email=f"platform-{suffix}@example.com",
            organization_name=org_a.name,
            organization_id=org_a.id,
            status="new",
        )
        db.add_all([own, other, privileged])
        db.commit()
        own_id, other_id, privileged_id = own.id, other.id, privileged.id
    finally:
        db.close()

    token = _login(f"tpo-a-{suffix}@example.com", password)
    response = client.get("/institutions/access-requests", headers=_auth(token))
    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()}
    assert own_id in ids
    assert other_id not in ids
    assert privileged_id not in ids

    response = client.patch(
        f"/institutions/access-requests/{own_id}",
        headers=_auth(token),
        json={"status": "approved", "review_note": "Institution verified recruiter request."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"

    cross_tenant = client.patch(
        f"/institutions/access-requests/{other_id}",
        headers=_auth(token),
        json={"status": "approved"},
    )
    assert cross_tenant.status_code == 404

    privileged_update = client.patch(
        f"/institutions/access-requests/{privileged_id}",
        headers=_auth(token),
        json={"status": "approved"},
    )
    assert privileged_update.status_code == 404


def test_institution_access_frontend_is_core_owned_and_mirrored() -> None:
    app_runtime = (ROOT / "app/static/workspace-runtime.js").read_text(encoding="utf-8")
    public_runtime = (ROOT / "public/static/workspace-runtime.js").read_text(encoding="utf-8")
    app_core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    public_core = (ROOT / "public/static/app-core.js").read_text(encoding="utf-8")

    assert app_runtime == public_runtime
    assert app_core == public_core
    assert "loadInstitutionAccessWorkspace();" not in app_runtime
    assert "['Access','institution-access-requests','Access requests']" in app_core
    assert "if (view === 'institution-access-requests')" in app_core
    assert "const rows = await api('/institutions/access-requests');" in app_core
    assert "data-institution-access-status" in app_core
