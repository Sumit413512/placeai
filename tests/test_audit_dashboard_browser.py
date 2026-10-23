"""Reproduce the reported action-label failure at real responsive widths."""
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_page_layout_browser import layout_accounts  # noqa: F401


def test_dashboard_action_labels_do_not_stack_vertically(browser, layout_accounts):
    context = browser.new_context(reduced_motion='reduce')
    email, password = layout_accounts['student']
    login = context.request.post(BASE_URL+'/auth/login-json', data={'email':email,'password':password})
    assert login.status == 200
    page = context.new_page()
    page.goto(BASE_URL, wait_until='networkidle')
    action = page.locator('#app-content .activity-item .row-actions button[data-view="profile"]')
    action.wait_for(state='visible')
    for width in (320, 390, 768, 1440):
        page.set_viewport_size({'width':width,'height':960})
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        rect = action.bounding_box()
        assert rect['width'] >= 72 and rect['height'] <= 55, (width,rect)
        assert action.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert '100%' not in page.locator('.metric-card').first.inner_text()
    context.close()
