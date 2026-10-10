from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_optional_analytics_require_consent_and_can_be_withdrawn(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 390, "height": 844})
    events = []
    page.route(
        "**/telemetry/page-view", lambda route: (events.append(route.request.post_data_json), route.fulfill(status=204))
    )
    page.goto(BASE_URL, wait_until="networkidle")
    assert not events
    assert page.evaluate("localStorage.getItem('placeai_visitor_id')") is None
    page.get_by_role("button", name="Essential only", exact=True).click()
    page.reload(wait_until="networkidle")
    assert not events
    assert page.locator("#privacy-preferences").is_hidden()
    page.get_by_role("button", name="Privacy choices", exact=True).click()
    page.get_by_role("button", name="Allow optional analytics", exact=True).click()
    page.wait_for_function("localStorage.getItem('placeai_visitor_id') !== null")
    assert events
    assert all("?" not in event["path"] for event in events)
    page.get_by_role("button", name="Privacy choices", exact=True).click()
    page.get_by_role("button", name="Essential only", exact=True).click()
    assert page.evaluate("localStorage.getItem('placeai_visitor_id')") is None
    page.locator('.hero button[data-open-auth="login"]').click()
    assert page.locator("#auth-overlay").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.close()
