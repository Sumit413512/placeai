from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_learning_hub import chapter_data, plan_data, preferences


def test_student_can_create_read_and_download_notes_without_leaving_workspace(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    submitted = []
    ready = {"id": "browser-notebook-001", "title": "SQL study notebook", "status": "ready",
             "completed_chapters": 8, "total_chapters": 8, "input": preferences(),
             "pdf_available": True, "plan": plan_data(), "chapters": [chapter_data()],
             "sources": [{"title": "PostgreSQL SELECT", "url": "https://www.postgresql.org/docs/current/sql-select.html"}]}
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
            if route.request.method == "POST": submitted.append(route.request.post_data_json); data = ready
            else: data = {"generation_available": True, "items": [ready] if submitted else []}
        elif path.endswith("/pdf"):
            route.fulfill(body=b"%PDF-1.4\nBrowser download transport check", content_type="application/pdf"); return
        elif path.startswith("/learning-hub/"): data = ready
        route.fulfill(json=data)
    page.route(BASE_URL + "/**", api)
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator('#app-nav [data-view="learning-hub"]').click()
    page.get_by_label("Topic or subject", exact=True).fill("SQL")
    page.get_by_label("Programming language or tool", exact=True).fill("PostgreSQL")
    page.get_by_label("What should your notes cover?", exact=True).fill("Queries, joins and transactions with explanations")
    page.get_by_role("button", name="Research and create detailed notes", exact=True).click()
    page.locator(".learning-chapter").first.wait_for(state="visible")
    assert submitted[0]["chapters"] == 12 and submitted[0]["programming_language"] == "PostgreSQL"
    assert len(submitted) == 1
    assert page.locator(".learning-relationship").count() == 2
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
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator('#app-nav [data-view="opportunities"]').click()
    assert not page.locator("#learning-hub").count()
    page.close()
