from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_learning_journey_is_readable_responsive_and_links_to_existing_flows(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(BASE_URL, wait_until="networkidle")
    heading = page.locator("#recruiters .section-heading h2")
    assert heading.evaluate("el=>getComputedStyle(el).fontWeight") == "400"
    assert "Calibri" in heading.evaluate("el=>getComputedStyle(el).fontFamily")
    assert page.locator(".journey-card h3").all_text_contents() == ["Learn", "Practise", "Get placed"]
    assert page.locator(".journey-card a").evaluate_all("els=>els.map(el=>el.getAttribute('href'))") == [
        "#preparation-lab",
        "#preparation-lab",
        "#institutions",
    ]
    assert (
        page.locator(".journey-card").first.evaluate("el=>getComputedStyle(el,'::before').animationName")
        == "placeaiJourneyHighlight"
    )
    for width in (1440, 736, 390, 320):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        for title in page.locator(".journey-card h3").all():
            assert title.is_visible()
            assert title.evaluate("el=>getComputedStyle(el).fontWeight") == "400"
    page.emulate_media(reduced_motion="reduce")
    assert page.locator(".journey-card").first.evaluate("el=>getComputedStyle(el,'::before').animationName") == "none"
    page.locator(".journey-card a").first.click()
    assert page.url.endswith("#preparation-lab")
    page.locator('.hero button[data-open-auth="login"]').click()
    assert page.locator("#auth-overlay").is_visible()
    page.close()
