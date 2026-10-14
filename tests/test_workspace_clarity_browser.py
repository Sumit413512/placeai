import json
from pathlib import Path

import pytest

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


@pytest.mark.parametrize('role', ['student', 'recruiter', 'institution_admin', 'platform_admin'])
def test_workspace_identity_and_navigation_remain_clear(browser, role):
    page = browser.new_page(viewport={'width': 1440, 'height': 960})

    def api_response(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        if path.startswith('/static/'):
            route.continue_()
            return
        if path == '/auth/me':
            data = {'id': 'ui-review', 'username': 'MIT account', 'email': 'ui@example.test', 'role': role}
        elif path == '/enterprise/notifications':
            data = {'items': [], 'unread': 0}
        elif path == '/learning-hub':
            data = {'items': [], 'generation_available': True}
        elif path.endswith('/applications'):
            data = [{'id': 'ui-application', 'job_title': 'Graduate engineer', 'company_name': 'Example company',
                     'applied_at': '2026-10-13T10:00:00Z', 'status': 'applied',
                     'student': {'full_name': 'Review student', 'college': 'Example institution'}}]
        elif path.endswith(('/jobs', '/students', '/organizations', '/notebooks')):
            data = []
        elif path.endswith('/dashboard'):
            data = {'active_jobs': 0, 'applications': 0, 'interviews': 0,
                    'shortlisted': 0, 'offers': 0, 'hired': 0, 'verified': True,
                    'organizations': 0, 'students': 0, 'recruiters': 0,
                    'total_applications': 0, 'placement_rate': 0, 'hires': 0,
                    'organization': {'name': 'MIT'}, 'total_students': 0, 'verified_students': 0}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/enterprise/**', '**/students/**', '**/recruiters/**',
                    '**/institutions/**', '**/platform/**', '**/billing/**', '**/ai/**',
                    '**/jobs/**', '**/intelligence/**', '**/learning-hub*'):
        page.route(pattern, api_response)
    page.goto(BASE_URL, wait_until='networkidle')
    page.locator('#app-shell').wait_for(state='visible')
    assert page.locator('#sidebar-user-name').inner_text() == 'MIT account'
    assert page.locator('#workspace-name').is_hidden()
    assert page.locator('#sidebar-user-role').is_hidden()
    assert page.locator('.workspace-role-chip').count() == 0
    if role != 'institution_admin':
        assert page.locator('#page-eyebrow').is_hidden()
    assert page.locator('#app-nav button[aria-current="page"]').count() == 1

    if role in ('student', 'institution_admin'):
        page.locator('#app-nav button[data-view="applications"]').click()
        page.locator('.page-head h1').wait_for()
        assert page.locator('#page-title').inner_text() == 'Applications'
        if role == 'student':
            assert page.locator('#page-eyebrow').is_hidden()
        assert page.locator('#app-nav button[aria-current="page"]').get_attribute('data-view') == 'applications'
        assert page.locator('.status-applied').evaluate('el => getComputedStyle(el).color') == 'rgb(89, 65, 111)'
    if role == 'student':
        page.locator('#app-nav button[data-view="learning-hub"]').click()
        page.locator('#learning-hub').wait_for()
        assert page.locator('#page-title').inner_text() == 'Learning Hub'
        assert page.locator('#page-eyebrow').is_hidden()
        assert page.locator('.workspace-role-chip').count() == 0
        assert page.locator('#learning-hub input[name="topic"]').is_visible()
    assert page.locator('.account-security-button, [data-auth-protection]').count() == 0
    sign_out = page.locator('[data-action="logout"]').first
    page.keyboard.press('Tab')
    sign_out.focus()
    assert sign_out.evaluate('el => getComputedStyle(el).outlineStyle') != 'none'

    output = Path(__file__).resolve().parents[1] / 'work/ui-review'
    output.mkdir(parents=True, exist_ok=True)
    metrics = page.locator('#app-shell').evaluate('''shell => {
      const nodes = [...shell.querySelectorAll('*')].filter(el =>
        el.getClientRects().length && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
      return {
        fontSizes: [...new Set(nodes.map(el => getComputedStyle(el).fontSize))],
        textColours: [...new Set(nodes.map(el => getComputedStyle(el).color))]
      };
    }''')
    (output / f'{role}-metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    page.screenshot(path=str(output / f'{role}-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_timeout(100)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(output / f'{role}-mobile.png'), full_page=True)
    page.close()
