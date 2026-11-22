from playwright.sync_api import expect

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_arrays_practice_is_available_in_video_learning_and_submits_answers(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    submitted = []

    def mock(route):
        request = route.request
        path = request.url.removeprefix(BASE_URL).split("?", 1)[0]
        if request.resource_type not in {"fetch", "xhr"}:
            route.continue_()
            return
        data = {"items": []}
        if path == "/auth/refresh":
            data = {"access_token": "test"}
        elif path == "/auth/me":
            data = {"id": "arrays-student", "username": "Arrays learner", "role": "student"}
        elif path in {"/students/applications", "/students/jobs"}:
            data = []
        elif path == "/billing/status":
            data = {"student_kind": "university", "premium_access": True}
        elif path.startswith("/array-readiness/me"):
            if request.method == "POST":
                submitted.append(request.post_data_json)
            data = {
                "track": "personal", "institution": None,
                "lesson_url": "/?view=learning-hub&course=demo&lesson=2&t=76",
                "step": "practice" if submitted else "diagnostic",
                "question": {"prompt": "Select the index", "code": "values = [8, 14]", "options": ["0", "1"]},
                "results": {"diagnostic": {"correct": False, "feedback": "Count from zero."}} if submitted else {},
            }
        route.fulfill(json=data)

    page.route(BASE_URL + "/**", mock)
    try:
        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("button", name="Essential only", exact=True).click()
        page.locator(".sidebar-trigger").click()
        page.locator('#app-nav button[data-view="learning-hub"]').click()
        page.get_by_role("button", name="Video learning", exact=True).click()
        page.get_by_role("button", name="Open Arrays practice").click()
        page.get_by_role("radio", name="0", exact=True).check()
        page.get_by_role("button", name="Save answer").click()
        expect(page.get_by_text("Count from zero.", exact=False)).to_be_visible()
        expect(page.get_by_role("link", name="Indexed Access & Safety (opens in a new tab)")).to_have_attribute(
            "href", "/?view=learning-hub&course=demo&lesson=2&t=76",
        )
        assert submitted == [{"step": "diagnostic", "track": "personal", "choice": 0}]
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    finally:
        page.close()
