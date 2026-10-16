from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_learning_journey_is_readable_responsive_and_links_to_existing_flows(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("button", name="Essential only", exact=True).click()
    assert page.locator(".hero h1").inner_text().replace("\n", " ") == "Placement operations, connected end to end."
    assert page.locator(".hero-journey-line").inner_text() == "Learn · Practice · Get Placed"
    page.locator('#marketing-site .site-header .brand').focus()
    page.keyboard.press('Shift+Tab')
    skip = page.get_by_role('link', name='Skip to main content', exact=True)
    assert skip.evaluate('el=>el===document.activeElement')
    assert skip.bounding_box()['y'] >= 0
    page.keyboard.press('Enter')
    page.wait_for_function("document.activeElement.id === 'top'")
    levels = page.locator('#marketing-site h1, #marketing-site h2, #marketing-site h3').evaluate_all(
        'els=>els.filter(el=>el.getClientRects().length).map(el=>Number(el.tagName[1]))')
    assert all(current <= previous + 1 for previous, current in zip(levels, levels[1:])), levels
    heading = page.locator("#recruiters .section-heading h2")
    assert heading.evaluate("el=>getComputedStyle(el).fontWeight") == "400"
    assert "Calibri" in heading.evaluate("el=>getComputedStyle(el).fontFamily")
    assert page.locator(".journey-card h3").all_text_contents() == ["Learn", "Practice", "Get Placed"]
    assert page.locator(".journey-card a").evaluate_all("els=>els.map(el=>el.getAttribute('href'))") == [
        "#preparation-lab",
        "#preparation-lab",
        "#institutions",
    ]
    assert (
        page.locator(".journey-card").first.evaluate("el=>getComputedStyle(el,'::before').animationName")
        == "placeaiJourneyHighlight"
    )
    assert page.locator('.journey-card').first.evaluate("el=>getComputedStyle(el,'::before').animationIterationCount") == '1'
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
    assert page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == 'auto'
    assert page.locator('#preparation-lab').bounding_box()['y'] >= 76
    sign_in = page.get_by_role('button', name='Sign in to PlaceAI', exact=True)
    assert sign_in.locator('svg').get_attribute('aria-hidden') == 'true'
    assert sign_in.bounding_box()['height'] >= 44
    page.keyboard.press('Tab')
    sign_in.focus()
    assert sign_in.evaluate("el=>getComputedStyle(el).outlineStyle") != 'none'
    page.keyboard.press('Enter')
    assert page.locator("#auth-overlay").is_visible()
    from pathlib import Path
    page.locator('[data-action="close-auth"]').click()
    icon = page.locator('.placeai-social-button svg')
    assert icon.bounding_box()['width'] <= 24
    assert icon.bounding_box()['height'] <= 24
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.evaluate("document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0)")
    output = Path(__file__).resolve().parents[1] / 'work/ui-review'
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / 'homepage-design-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(output / 'homepage-design-mobile.png'), full_page=True)
    page.close()
