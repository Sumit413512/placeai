"""Exercise every role navigation page against a real, isolated local database."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Application, Job, Organization, PlacementDrive, RecruiterProfile, StudentProfile, User, UserRole
from app.utils import get_hashed_password
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


@pytest.fixture(scope="module")
def layout_accounts(local_server):
    password = "Isolated layout verification 2026!"
    engine = create_engine(f"sqlite:///{local_server}")
    accounts = {}
    with Session(engine) as db:
        org = Organization(name="Northstar Institute of Engineering and Applied Technology", slug="layout-"+uuid4().hex)
        db.add(org)
        db.flush()
        for role in UserRole:
            user = User(email=f"layout-{role.value}@example.com", username="layout-"+role.value,
                        role=role, email_verified=True, hashed_password=get_hashed_password(password),
                        organization_id=org.id if role != UserRole.platform_admin else None)
            db.add(user)
            db.flush()
            accounts[role.value] = (user.email, password)
            if role == UserRole.student:
                student = StudentProfile(user_id=user.id, organization_id=org.id, full_name="Layout Review Student",
                                         college=org.name, branch="Computer Science and Engineering", cgpa=8.2,
                                         graduation_year=2027, is_verified=True, skills_json='["Python","SQL"]')
                db.add(student)
            elif role == UserRole.recruiter:
                recruiter = RecruiterProfile(user_id=user.id, full_name="Layout Review Recruiter",
                                             company_name="Northstar Enterprise Software and Infrastructure",
                                             is_verified=True, provisioned_by_organization_id=org.id)
                db.add(recruiter)
        db.flush()
        job = Job(recruiter_id=recruiter.id, title="Graduate Software Engineer — Data Platforms and Infrastructure",
                  description="Build reliable data platforms with Python and SQL. Work with the engineering team.",
                  location="Bengaluru / Hybrid", visibility="campus", target_organization_id=org.id)
        db.add(job)
        db.flush()
        db.add(Application(student_id=student.id, job_id=job.id))
        db.add(PlacementDrive(organization_id=org.id, job_id=job.id,
                              title="Graduate engineering placement drive — software and data platforms"))
        db.commit()
    engine.dispose()
    return accounts


@pytest.mark.parametrize("role", ["student", "recruiter", "institution_admin", "platform_admin"])
def test_every_workspace_page_remains_readable_and_operable(browser, layout_accounts, role):
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    context.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    email, password = layout_accounts[role]
    response = context.request.post(BASE_URL+"/auth/login-json", data={"email": email, "password": password})
    assert response.status == 200, response.text()
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator("#app-shell").wait_for(state="visible")
    views = page.locator("#app-nav [data-view]").evaluate_all("els => els.map(el => el.dataset.view)")
    output = Path(__file__).resolve().parents[1] / "work/page-layout-audit" / role
    output.mkdir(parents=True, exist_ok=True)
    findings = []
    for view in views:
        page.set_viewport_size({"width": 1440, "height": 1000})
        if "/mock-interview" in page.url:
            page.goto(BASE_URL, wait_until="networkidle")
        button = page.locator(f'#app-nav [data-view="{view}"]')
        if not button.is_visible():
            page.locator(".placeai-nav-more").click()
        button.click()
        if view == "mock-interview":
            page.wait_for_url("**/mock-interview")
            root = page.locator("main.shell")
            root.locator("h1").wait_for(state="visible")
        else:
            page.locator("#app-content .page-head").wait_for(state="visible")
            root = page.locator("#app-content")
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            # Chromium can acknowledge resize before the new layout is painted.
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            measurements = root.evaluate("""root => {
              const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
              const controls = [...root.querySelectorAll('button,input:not([type=hidden]),select,textarea')].filter(visible);
              return {
                overflow: document.documentElement.scrollWidth > innerWidth + 1,
                outside: [...root.querySelectorAll('*')].filter(visible).filter(el => {
                  const rect = el.getBoundingClientRect();
                  return rect.width && (rect.right > innerWidth + 2 || rect.left < -2) &&
                    !el.closest('.table-wrap,.enterprise-table-wrap,pre');
                }).slice(0,8).map(el => ({tag:el.tagName, cls:el.className})),
                clippedMobileTables: innerWidth <= 760 ? [...root.querySelectorAll('table[data-placeai-responsive="true"]')]
                  .filter(el => el.getBoundingClientRect().width > el.parentElement.clientWidth + 2)
                  .map(el => ({width:el.getBoundingClientRect().width, parentWidth:el.parentElement.clientWidth, display:getComputedStyle(el).display})) : [],
                clippedButtons: controls.filter(el => el.tagName === 'BUTTON' && el.scrollWidth > el.clientWidth + 2 &&
                  getComputedStyle(el).textOverflow !== 'ellipsis').map(el => el.textContent.trim()),
                tinyControls: controls.filter(el => {
                  const r = el.getBoundingClientRect();
                  return !['checkbox','radio','file','range'].includes(el.type) && r.height < 24;
                }).map(el => ({tag:el.tagName, text:el.textContent.trim()})),
                title: root.querySelector('h1')?.textContent,
                errorState: Boolean(root.querySelector('[data-action="retry-view"]'))
              };
            }""")
            findings.append({"view": view, "width": width, **measurements})
            if width in (1440, 390):
                page.screenshot(path=str(output / f"{view}-{width}.png"), full_page=True)
    (output / "measurements.json").write_text(json.dumps({"pages": findings, "errors": errors}, indent=2), encoding="utf-8")
    assert not errors, errors
    failures = [f for f in findings if f["overflow"] or f["clippedButtons"] or f["tinyControls"] or f["errorState"] or f["clippedMobileTables"]]
    assert not failures, json.dumps(failures, indent=2)
    if role in {"platform_admin", "institution_admin", "recruiter"}:
        view = {"platform_admin": "organizations", "institution_admin": "students", "recruiter": "jobs"}[role]
        page.set_viewport_size({"width": 1440, "height": 1000})
        button = page.locator(f'#app-nav [data-view="{view}"]')
        if not button.is_visible():
            page.locator(".placeai-nav-more").click()
        button.click()
        page.locator("#app-content .page-head").wait_for(state="visible")
        page.locator("#context-action").click()
        dialog = page.locator("#generic-modal")
        dialog.wait_for(state="visible")
        for width in (1440, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            assert not dialog.evaluate("el => el.scrollWidth > el.clientWidth + 2")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(output / "create-dialog-mobile.png"), full_page=True)
        page.keyboard.press("Escape")
        dialog.wait_for(state="hidden")
    context.close()


def test_public_pages_fit_mobile_and_desktop(browser):
    page = browser.new_page(reduced_motion="reduce")
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    output = Path(__file__).resolve().parents[1] / "work/page-layout-audit/public"
    output.mkdir(parents=True, exist_ok=True)
    paths = ["/", "/privacy", "/terms", "/acceptable-use", "/static/about.html", "/static/contact.html",
             "/static/pricing.html", "/static/refund-cancellation.html", "/static/service-delivery.html", "/404"]
    for index, path in enumerate(paths):
        response = page.goto(BASE_URL+path, wait_until="networkidle")
        assert response.status == (404 if path == "/404" else 200)
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (path, width)
        page.screenshot(path=str(output / f"page-{index}-mobile.png"), full_page=True)
    page.close()


def test_production_bootstrap_deduplicates_versioned_assets(browser, layout_accounts):
    """Vercel serves the public bootstrap; Render serves the canonical core."""
    root = Path(__file__).resolve().parents[1]
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    context.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    email, password = layout_accounts["student"]
    response = context.request.post(BASE_URL+"/auth/login-json", data={"email":email, "password":password})
    assert response.status == 200
    page = context.new_page()
    bootstrap = (root / "public/static/app.js").read_text(encoding="utf-8")
    # A cached shell and a fresh bootstrap can legitimately use different versions.
    bootstrap = bootstrap.replace("workspace-experience.js?v=20261016-interface-guidelines",
                                  "workspace-experience.js?v=next-release")
    page.route("**/static/app.js?*", lambda route: route.fulfill(body=bootstrap, content_type="text/javascript"))
    page.route("**/static/app-core.js?*", lambda route: route.fulfill(
        body=(root / "public/static/app-core.js").read_bytes(), content_type="text/javascript"))
    page.goto(BASE_URL, wait_until="networkidle")
    nav = page.locator("#app-nav")
    nav.locator(".placeai-nav-more").wait_for(state="visible")
    nav.locator(".placeai-nav-more").click()
    assert nav.get_attribute("data-placeai-more-open") == "true"
    assert nav.locator('[data-view="documents"]').is_visible()
    nav.locator('[data-view="documents"]').click()
    page.get_by_role("heading", name="Student document vault", exact=True).wait_for(state="visible")
    assert page.locator('script[src*="workspace-experience.js"]').count() == 1
    assert page.locator('script[src*="app-core.js"]').count() == 1
    nav.locator(".placeai-nav-more").click()
    assert nav.get_attribute("data-placeai-more-open") == "false"
    context.close()
