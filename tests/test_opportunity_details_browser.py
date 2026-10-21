import json
import os
from pathlib import Path

from playwright.sync_api import expect
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from app.opportunity_detail import demo_opportunity


def test_opportunity_detail_demo_and_application_flow(browser):
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    job = {"id": "real-job", "title": "Graduate Software Engineer", "company_name": "Published Company",
           "description": "Build reliable software.\n\n<img src=x onerror=window.detailInjected=true>\nThis text must remain literal.",
           "required_skills": ["SQL", "Python"], "job_type": "Full-time", "location": "Pune", "salary_range": "INR 5 LPA",
           "experience_required": "0–1 year", "created_at": "2026-10-21T08:00:00", "deadline": "2027-01-21T10:00:00",
           "visibility": "campus", "is_demo": False, "is_preview": False,
           "company": {"name": "Published Company", "industry": "Software", "website": "javascript:alert(1)", "contact": "Placement office"},
           "criteria": [{"label": "Minimum CGPA", "value": "6.5"}], "selection_process": ["Assessment", "Technical interview"],
           "eligibility": {"eligible": True, "summary": "You meet the published drive criteria.", "reasons": []},
           "policy": {"allowed": True, "reasons": []}, "registration_notes": "Read the published description before applying.",
           "can_apply": True, "already_applied": False}
    applied = []; jobs = [job]; delayed = []; delay = [False]; requests = []
    def api(route):
        path = route.request.url.split(BASE_URL)[-1].split('?')[0]
        requests.append(path)
        if route.request.resource_type not in {"fetch", "xhr"}: route.continue_(); return
        data = {"items": [], "summary": {}, "actions": []}
        if path == '/auth/refresh': data = {"access_token": "local-opportunity-token"}
        elif path == '/auth/me': data = {"id": "preview", "username": "Preview student", "role": "student", "email": "preview@example.invalid"}
        elif path == '/billing/status': data = {"student_kind": "university", "premium_access": True}
        elif path == '/students/jobs': data = jobs
        elif path == '/students/applications': data = [{"id": "application", "job_id": "real-job", "job_title": job['title'], "company_name": job['company_name'], "status": "applied"}] if applied else []
        elif path == '/students/jobs/real-job':
            if delay[0]: delayed.append(route); return
            data = {**job, "already_applied": bool(applied), "can_apply": not applied}
        elif path == '/students/opportunity-demo': data = demo_opportunity()
        elif path == '/students/jobs/real-job/apply':
            applied.append(route.request.post_data_json); data = {"id": "application", "status": "applied"}
        route.fulfill(content_type='application/json', body=json.dumps(data))
    page.route(BASE_URL+'/**', api)
    page.goto(BASE_URL, wait_until='networkidle')
    page.locator('#app-nav [data-view="opportunities"]').click()
    try:
        page.locator('#job-search').wait_for(timeout=8000)
    except Exception as error:
        raise AssertionError((page.locator('#app-content').inner_text(), requests)) from error
    page.locator('#job-search').fill('Software')
    page.get_by_role('button', name='View details', exact=True).click()
    expect(page.locator('.opportunity-heading h1')).to_have_text(job['title'])
    assert page.locator('.opportunity-hero>img').get_attribute('src') == '/static/opportunity-workplace.webp'
    assert page.locator('.opportunity-description img').count() == 0
    assert page.evaluate('window.detailInjected === undefined')
    assert page.locator('.opportunity-sidebar a[href^="javascript:"]').count() == 0
    assert page.get_by_role('heading', name='Eligibility criteria', exact=True).is_visible()
    assert page.get_by_role('heading', name='About the organization', exact=True).is_visible()
    assert 'IST' in page.locator('.opportunity-schedule').first.inner_text()
    for width in (1600, 1440, 1100, 768, 390, 320):
        page.set_viewport_size({"width": width, "height": 1050})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        assert page.get_by_role('button', name='Apply now', exact=True).is_visible()
    page.set_viewport_size({"width": 1600, "height": 1050})
    page.get_by_role('button', name='Apply now', exact=True).click()
    page.get_by_role('textbox', name='Cover note optional').fill('Interested in the published role')
    page.get_by_role('button', name='Submit application', exact=True).click()
    expect(page.locator('#app-content h1')).to_have_text('Application pipeline')
    assert applied == [{"cover_note": "Interested in the published role"}]
    page.locator('#app-nav [data-view="opportunities"]').click()
    assert page.get_by_role('searchbox', name='Search opportunities').input_value() == 'Software'
    page.get_by_role('button', name='View details', exact=True).click()
    expect(page.get_by_role('button', name='Applied', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Opportunity list', exact=True).click()
    page.get_by_role('button', name='View TechNova demo', exact=True).click()
    expect(page.locator('.opportunity-heading h1')).to_contain_text('Demo')
    assert page.locator('.opportunity-logo img').get_attribute('src') == '/static/technova-demo.svg'
    assert page.locator('.opportunity-demo-notice').inner_text().startswith('TechNova is a fictional')
    expect(page.locator('.toast')).to_have_count(0, timeout=6000)
    directory = os.getenv('PLACEAI_OPPORTUNITY_SCREENSHOTS')
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(directory)/'technova-desktop.png'), full_page=True, animations='disabled')
        page.set_viewport_size({"width":390,"height":900})
        page.wait_for_function("() => document.querySelector('.app-sidebar').getBoundingClientRect().right <= 0")
        page.screenshot(path=str(Path(directory)/'technova-mobile.png'), full_page=True, animations='disabled')
        page.set_viewport_size({"width":1600,"height":1050})
    page.get_by_role('button', name='Preview demo application', exact=True).click()
    expect(page.get_by_role('heading', name='Fictional demo application', exact=True)).to_be_visible()
    assert len(applied) == 1
    page.get_by_role('button', name='Close dialog', exact=True).click()
    page.get_by_role('button', name='Opportunity list', exact=True).click()
    delay[0] = True
    page.get_by_role('button', name='View details', exact=True).click()
    expect(page.get_by_role('status').filter(has_text='Loading opportunity')).to_be_visible()
    page.locator('#app-nav [data-view="applications"]').click()
    expect(page.locator('#app-content h1')).to_have_text('Application pipeline')
    delayed[0].fulfill(json=job)
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    assert page.locator('.opportunity-detail').count() == 0
    jobs.clear(); delay[0] = False
    page.locator('#app-nav [data-view="opportunities"]').click()
    expect(page.get_by_role('heading', name='No open opportunities', exact=True)).to_be_visible()
    assert page.locator('#job-result-count').inner_text() == '0 opportunities'
    assert page.get_by_role('button', name='View TechNova demo', exact=True).is_visible()
    page.close()
