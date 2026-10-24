
from playwright.sync_api import expect

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_page_layout_browser import layout_accounts  # noqa: F401


def signed_context(browser, layout_accounts):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    email, password = layout_accounts['student']
    response = context.request.post(BASE_URL + '/auth/login-json', data={'email': email, 'password': password})
    assert response.status == 200, response.text()
    return context


def test_back_from_video_learning_uses_workspace_history_not_old_mock_page(browser, layout_accounts):
    context = signed_context(browser, layout_accounts)
    page = context.new_page()
    page.route('https://**/*', lambda route: route.abort())
    page.goto(BASE_URL + '/mock-interview', wait_until='domcontentloaded')
    page.get_by_role('link', name='Back to PlaceAI', exact=True).click()
    expect(page.locator('#app-shell')).to_be_visible()
    page.locator('#app-nav [data-view="applications"]').click()
    expect(page).to_have_url(BASE_URL + '/?view=applications')
    page.locator('#app-nav [data-view="learning-hub"]').click()
    page.get_by_role('button', name='Video learning', exact=True).click()
    expect(page.locator('[data-video-discovery]')).to_be_visible()
    page.go_back()
    expect(page.locator('#app-nav [data-view="applications"]')).to_have_class('active')
    expect(page).to_have_url(BASE_URL + '/?view=applications')
    page.go_forward()
    expect(page.locator('#learning-hub')).to_be_visible()
    expect(page).to_have_url(BASE_URL + '/?view=learning-hub')
    page.reload(wait_until='networkidle')
    expect(page.locator('#learning-hub')).to_be_visible()
    expect(page.locator('#auth-overlay')).to_be_hidden()
    context.close()
