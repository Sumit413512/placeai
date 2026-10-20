from playwright.sync_api import expect

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_learning_hub import plan_data, preferences
from test_learning_notes_advanced import advanced_chapter


def test_student_can_create_read_and_download_notes_without_leaving_workspace(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    submitted = []
    phase = ["running"]
    ready = {"id": "browser-notebook-001", "title": "SQL study notebook", "status": "ready",
             "completed_chapters": 8, "total_chapters": 8, "input": preferences(),
             "pdf_available": True, "plan": plan_data(), "chapters": [advanced_chapter()],
             "sources": [{"title": "PostgreSQL SELECT", "url": "https://www.postgresql.org/docs/current/sql-select.html"}]}
    ready["chapters"][0]["overview"] += " **Safe term** <img src=x onerror=window.notesInjected=true>"
    def api(route):
        path = route.request.url.split(BASE_URL)[-1].split("?")[0]
        if route.request.resource_type not in {"fetch", "xhr"}:
            route.continue_(); return
        data = {"items": [], "summary": {}, "actions": []}
        if path == "/auth/refresh": data = {"access_token": "local-preview-token"}
        elif path == "/auth/me": data = {"id": "preview-student", "role": "student", "email": "preview@example.invalid", "username": "Preview student"}
        elif path in {"/students/applications", "/students/jobs"}: data = []
        elif path == "/billing/status": data = {"student_kind": "university", "premium_access": True, "access_mode": "institution_sponsored"}
        elif path == "/learning-hub":
            if route.request.method == "POST": submitted.append(route.request.post_data_json); data = {**ready,"status":phase[0],"completed_chapters":1,"pdf_available":False}
            else: data = {"generation_available": True, "items": [{**ready,"status":phase[0],"completed_chapters":1 if phase[0] != "ready" else 8,"pdf_available":phase[0] == "ready"},{**ready,"id":"failed-notebook","title":"Failed notes","status":"failed"}] if submitted else []}
        elif path.endswith("/pdf"):
            route.fulfill(body=b"%PDF-1.4\nBrowser download transport check", content_type="application/pdf"); return
        elif path.startswith("/learning-hub/"): data = ready if phase[0] == "ready" else {**ready,"status":phase[0],"completed_chapters":1,"pdf_available":False}
        route.fulfill(json=data)
    page.route(BASE_URL + "/**", api)
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator('#app-nav [data-view="learning-hub"]').click()
    page.get_by_label("Topic or subject", exact=True).fill("SQL")
    page.get_by_label("Programming language or tool", exact=True).fill("PostgreSQL")
    page.get_by_label("What should your notes cover?", exact=True).fill("Queries, joins and transactions with explanations")
    page.get_by_role("button", name="Research and create detailed notes", exact=True).click()
    expect(page.locator("#learning-library")).to_contain_text("Processing")
    expect(page.locator("#learning-library")).not_to_contain_text("Failed notes")
    expect(page.locator(".learning-chapter")).to_have_count(0)
    expect(page.get_by_role("button",name="Download complete PDF",exact=True)).to_have_count(0)
    phase[0]="ready"
    page.get_by_role("button",name="Refresh",exact=True).click()
    expect(page.locator("#learning-library")).to_contain_text("Ready to begin")
    page.locator(".learning-chapter").first.wait_for(state="visible")
    assert submitted[0]["chapters"] == 12 and submitted[0]["programming_language"] == "PostgreSQL"
    assert len(submitted) == 1
    assert page.locator(".learning-relationship").count() == 2
    assert page.locator(".learning-chapter strong").filter(has_text="Predicate").first.inner_text() == "Predicate"
    assert page.locator(".learning-chapter ol li").count() >= 2
    assert page.get_by_role("columnheader", name="Clause", exact=True).is_visible()
    assert page.get_by_role("heading", name="Matching row percentage", exact=True).is_visible()
    assert page.get_by_role("heading", name="Quick revision", exact=True).is_visible()
    assert page.get_by_role("heading", name="What to learn next", exact=True).is_visible()
    assert page.locator(".learning-chapter img").count() == 0
    assert page.evaluate("window.notesInjected === undefined")
    assert page.locator(".learning-chapter code").first.inner_text().startswith("SELECT name")
    assert page.locator(".learning-citations a").first.get_attribute("href") == "#learning-source-1"
    page.get_by_text("Show solution and reasoning", exact=True).first.click()
    assert page.get_by_text("Use SELECT to choose columns", exact=False).first.is_visible()
    for width in (1440, 736, 390, 320):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, page.evaluate("[...document.querySelectorAll('#learning-hub *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])"))
        assert page.get_by_role("button", name="Download complete PDF", exact=True).is_visible()
    with page.expect_download() as download:
        page.get_by_role("button", name="Download complete PDF", exact=True).click()
    assert download.value.suggested_filename == "PlaceAI-Learning-Notes.pdf"
    phase[0]="failed"
    page.get_by_role("button",name="Refresh",exact=True).click()
    expect(page.locator("#learning-notebook-result")).to_be_empty()
    expect(page.locator("#learning-library [data-learning-id]")).to_have_count(0)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator('#app-nav [data-view="opportunities"]').click()
    assert not page.locator("#learning-hub").count()
    page.close()
