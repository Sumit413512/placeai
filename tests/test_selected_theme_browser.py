from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def test_selected_palette_survives_dynamic_styles_and_auth_dialog(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="networkidle")
    assert page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(245, 242, 236)"
    sidebar = page.locator(".app-sidebar")
    assert sidebar.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(223, 221, 221)"
    assert sidebar.evaluate("el => getComputedStyle(el).color") == "rgb(39, 35, 48)"
    assert (
        page.locator(".sidebar-bottom").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(223, 221, 221)"
    )
    sign_in = page.locator('.hero button[data-open-auth="login"]')
    sign_in.click()
    assert page.locator("#auth-overlay").is_visible()
    assert (
        page.locator("#auth-overlay .auth-brand-panel").evaluate("el => getComputedStyle(el).backgroundColor")
        == "rgb(223, 221, 221)"
    )
    for role in ("student", "recruiter", "institution_admin", "platform_admin"):
        page.locator(f'#login-view [data-access-role="{role}"]').click()
        assert page.locator('#role-login-form input[name="role"]').input_value() == role
        submit = page.locator('#role-login-form button[type="submit"]')
        page.mouse.move(0, 0)
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('#role-login-form button[type=submit]')).backgroundColor === 'rgb(89, 65, 111)'"
        )
        assert submit.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(89, 65, 111)"
        assert submit.evaluate("el => getComputedStyle(el).color") == "rgb(255, 255, 255)"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.close()


def test_theme_covers_assessment_and_legal_pages_without_revealing_hidden_panels(browser):  # noqa: F811
    page = browser.new_page(viewport={"width": 390, "height": 844})
    for path in ("/privacy", "/terms", "/acceptable-use", "/static/contact.html", "/mock-interview?preview=1"):
        page.goto(BASE_URL + path, wait_until="networkidle")
        assert page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(245, 242, 236)"
        if path.startswith("/mock-interview"):
            assert (
                page.locator(".assessment-sidebar").evaluate("el => getComputedStyle(el).backgroundColor")
                == "rgb(223, 221, 221)"
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
