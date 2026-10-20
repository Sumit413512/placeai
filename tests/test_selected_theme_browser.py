from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_selected_palette_survives_dynamic_styles_and_auth_dialog(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="networkidle")
    assert page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(246, 248, 252)"
    sidebar = page.locator(".app-sidebar")
    assert sidebar.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    assert sidebar.evaluate("el => getComputedStyle(el).color") == "rgb(23, 36, 59)"
    assert (
        page.locator(".sidebar-bottom").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(255, 255, 255)"
    )
    sign_in = page.locator('.hero button[data-open-auth="login"]')
    sign_in.click()
    assert page.locator("#auth-overlay").is_visible()
    assert (
        page.locator("#auth-overlay .auth-brand-panel").evaluate("el => getComputedStyle(el).backgroundColor")
        == "rgb(255, 255, 255)"
    )
    for role in ("student", "recruiter", "institution_admin", "platform_admin"):
        page.locator(f'#login-view [data-access-role="{role}"]').click()
        assert page.locator('#role-login-form input[name="role"]').input_value() == role
        submit = page.locator('#role-login-form button[type="submit"]')
        page.mouse.move(0, 0)
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('#role-login-form button[type=submit]')).backgroundColor === 'rgb(40, 89, 79)'"
        )
        assert submit.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(40, 89, 79)"
        assert submit.evaluate("el => getComputedStyle(el).color") == "rgb(255, 255, 255)"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.close()


def test_theme_covers_assessment_and_legal_pages_without_revealing_hidden_panels(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 390, "height": 844})
    for path in ("/privacy", "/terms", "/acceptable-use", "/static/contact.html", "/mock-interview?preview=1"):
        page.goto(BASE_URL + path, wait_until="networkidle")
        assert page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(246, 248, 252)"
        if path.startswith("/mock-interview"):
            assert (
                page.locator(".assessment-sidebar").evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgb(255, 255, 255)"
            )
            assert (
                page.locator(".proctor-header strong").evaluate("el => getComputedStyle(el).color")
                == "rgb(255, 255, 255)"
            )
            assert (
                page.locator(".assessment-camera-meta span").evaluate("el => getComputedStyle(el).color")
                == "rgb(255, 255, 255)"
            )
            assert page.locator("#result-panel").is_hidden()
            assert page.locator("#interview-panel").is_hidden()
        else:
            assert (
                page.locator(".legal-card").evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgb(255, 255, 255)"
            )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.close()


def _contrast(foreground, background):
    import re

    def luminance(colour):
        values = [int(v) / 255 for v in re.findall(r"[\d.]+", colour)[:3]]
        channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(channels, (.2126, .7152, .0722)))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + .05) / (dark + .05)


def test_editorial_cards_and_footer_remain_readable_on_mobile_and_desktop(browser):  # noqa: F811
    import os
    from pathlib import Path

    page = browser.new_page()
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(BASE_URL, wait_until="networkidle")
        footer = page.locator("#marketing-site .placeai-footer")
        footer.wait_for(state="visible")
        footer_bg = footer.evaluate("el => getComputedStyle(el).backgroundColor")
        assert footer_bg == "rgb(37, 59, 53)"
        for label in footer.locator("p, h3, a").all():
            if label.is_visible():
                colour = label.evaluate("el => getComputedStyle(el).color")
                assert _contrast(colour, footer_bg) >= 4.5
        assert page.locator(".hero h1 span").evaluate("el => getComputedStyle(el).color") == "rgb(23, 36, 59)"
        cards = page.locator(".journey-card")
        backgrounds = cards.evaluate_all("els => els.map(el => getComputedStyle(el).backgroundColor)")
        assert len(set(backgrounds)) == 3
        for card, background in zip(cards.all(), backgrounds):
            colour = card.locator("p").evaluate("el => getComputedStyle(el).color")
            assert _contrast(colour, background) >= 4.5
        primary = page.locator('.hero button[data-open-auth="login"]')
        colours = primary.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
        assert _contrast(*colours) >= 4.5
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert page.locator("#auth-overlay").is_hidden()
        assert page.locator("#app-shell").is_hidden()
        directory = os.getenv("PLACEAI_DESIGN_SCREENSHOTS")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(directory) / f"homepage-{width}.png"), full_page=True)
            consent = page.get_by_role("button", name="Essential only", exact=True)
            if consent.is_visible():
                consent.click()
            page.locator(".hero").scroll_into_view_if_needed()
            page.screenshot(path=str(Path(directory) / f"hero-{width}.png"))
            footer.scroll_into_view_if_needed()
            page.screenshot(path=str(Path(directory) / f"footer-{width}.png"))
    page.close()
