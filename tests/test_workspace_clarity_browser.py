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
            data = {'active_jobs': 0, 'applications': 12, 'interviews': 0,
                    'shortlisted': 0, 'offers': 0, 'hired': 0, 'verified': True,
                    'organizations': 0, 'students': 0, 'recruiters': 0,
                    'total_applications': 12, 'placement_rate': 76, 'hires': 8,
                    'profile_completion': 73, 'active_applications': 3, 'interviews_completed': 2,
                    'average_interview_score': 78, 'has_resume': True, 'open_drives': 4,
                    'organization': {'name': 'MIT'}, 'total_students': 0, 'verified_students': 0}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/enterprise/**', '**/students/**', '**/recruiters/**',
                    '**/institutions/**', '**/platform/**', '**/billing/**', '**/ai/**',
                    '**/jobs/**', '**/intelligence/**', '**/learning-hub*'):
        page.route(pattern, api_response)
    page.goto(BASE_URL, wait_until='networkidle')
    page.get_by_role('button', name='Essential only', exact=True).click()
    page.locator('#app-shell').wait_for(state='visible')
    assert page.locator('.workspace-welcome').inner_text() == 'Welcome, MIT account'
    if role == 'student':
        assert page.locator('#workspace-kind').inner_text() == 'STUDENT WORKSPACE'
        assert page.locator('#workspace-kind').evaluate('el => Number(getComputedStyle(el).fontWeight) >= 700')
    assert page.locator('.app-sidebar').get_by_text('MIT account', exact=True).count() == 0
    assert page.locator('#page-title').is_hidden()
    assert page.locator('#workspace-name').is_hidden()
    assert page.locator('#sidebar-user-role').is_hidden()
    assert page.locator('#workspace-avatar').is_hidden()
    logout = page.get_by_role('button', name='Sign out', exact=True)
    logout_box = logout.bounding_box()
    assert page.locator('.sidebar-bottom').get_by_role('button', name='Sign out', exact=True).is_visible()
    assert logout.evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(97, 39, 55)'
    assert logout.evaluate('el => getComputedStyle(el).color') == 'rgb(255, 248, 237)'
    assert logout_box['height'] >= 44
    assert logout.evaluate('el => parseFloat(getComputedStyle(el).borderTopWidth)') >= 1
    assert page.locator('.workspace-role-chip').count() == 0
    if role != 'institution_admin':
        assert page.locator('#page-eyebrow').is_hidden()
    assert page.locator('#app-nav button[aria-current="page"]').count() == 1

    page.locator('.sidebar-brand a').focus()
    page.keyboard.press('Shift+Tab')
    skip = page.get_by_role('link', name='Skip to workspace content', exact=True)
    assert skip.evaluate('el => el === document.activeElement')
    assert skip.bounding_box()['y'] >= 0
    page.keyboard.press('Enter')
    page.wait_for_function("document.activeElement.id === 'app-content'")

    cards = page.locator('.metric-grid .metric-card')
    assert cards.count() == (5 if role == 'platform_admin' else 4)
    assert page.locator('.workspace-shortcuts').count() == 1
    shortcuts = page.locator('.workspace-shortcut')
    assert shortcuts.count() == 4
    assert len(set(cards.evaluate_all('els => els.map(el => getComputedStyle(el).backgroundColor)'))) >= 2
    contrast = cards.evaluate_all(r'''els => {
      const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
      const lum = values => values.map(v => {v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;})
        .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      return els.flatMap(card => [...card.querySelectorAll('small, strong, span:not(.metric-symbol)')].map(el => {
        const fg = lum(rgb(getComputedStyle(el).color)), bg = lum(rgb(getComputedStyle(card).backgroundColor));
        return {text: el.textContent, ratio: (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05)};
      }));
    }''')
    assert all(item['ratio'] >= 4.5 for item in contrast), contrast
    assert cards.locator('.metric-symbol[aria-hidden="true"]').count() == cards.count()
    output = Path(__file__).resolve().parents[1] / 'work/ui-review'
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'{role}-dashboard-desktop.png'), full_page=True)
    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert shortcuts.evaluate_all('els => els.every(el => el.getBoundingClientRect().height >= 44)')
    page.screenshot(path=str(output / f'{role}-dashboard-mobile.png'), full_page=True)
    page.set_viewport_size({'width':1440,'height':960})
    target = shortcuts.first.get_attribute('data-view')
    page.keyboard.press('Tab')
    shortcuts.first.focus()
    assert shortcuts.first.evaluate('el => getComputedStyle(el).outlineStyle') != 'none'
    page.keyboard.press('Enter')
    page.wait_for_function("view => document.querySelector('#app-nav button.active')?.dataset.view === view", arg=target)
    page.locator('#app-nav button[data-view="dashboard"]').click()
    page.locator('.workspace-shortcuts').wait_for()
    assert page.locator('.workspace-shortcuts').count() == 1

    if role in ('student', 'institution_admin'):
        page.locator('#app-nav button[data-view="applications"]').click()
        page.locator('.page-head h1').wait_for()
        assert page.locator('#page-title').inner_text() == 'Applications'
        if role == 'student':
            assert page.locator('#page-eyebrow').is_hidden()
        assert page.locator('#app-nav button[aria-current="page"]').get_attribute('data-view') == 'applications'
        assert page.locator('.status-applied').evaluate('el => getComputedStyle(el).color') == 'rgb(159, 63, 36)'
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
    page.set_viewport_size({'width':1440,'height':960})
    with page.expect_request(lambda request: request.url == BASE_URL+'/auth/logout' and request.method == 'POST'):
        logout.click()
    page.close()


@pytest.mark.parametrize('width', [320, 1440])
def test_notifications_keep_dates_and_actions_readable(browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 900})

    def respond(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        if path == '/auth/me':
            data = {'id': 'notification-review', 'username': 'Review student', 'role': 'student'}
        elif path == '/enterprise/notifications':
            data = {'unread': 1, 'items': [{
                'id': 'update-1', 'is_read': False, 'title': 'Your video course is ready',
                'message': 'DSA Fundamentals passed the full course review and is ready to begin.',
                'category': 'learning', 'priority': 'high', 'link': 'learning-hub',
                'created_at': '2026-11-17T10:00:00Z',
            }]}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/enterprise/**', '**/billing/**', '**/ai/**'):
        page.route(pattern, respond)
    page.goto(BASE_URL + '/?view=notifications', wait_until='domcontentloaded')
    notice = page.locator('.notification-item')
    notice.wait_for()
    assert notice.locator('p').evaluate('el => parseFloat(getComputedStyle(el).fontSize) >= 16')
    date = notice.locator('time').bounding_box()
    button = notice.get_by_role('button', name='Open', exact=True).bounding_box()
    assert date['x'] + date['width'] < button['x'] or date['y'] + date['height'] < button['y']
    assert button['height'] >= 44
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.close()


def test_student_guidance_topbar_and_minimizable_report(browser):
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    signed_in = False
    submitted = []
    guide_dismissed = []

    def respond(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        data = {}
        if path in {'/auth/me', '/auth/refresh'} and not signed_in:
            route.fulfill(status=401, json={})
            return
        if path == '/auth/me':
            data = {'id': 'guidance-test', 'username': 'Tour student', 'role': 'student',
                    'workspace_guide_pending': not guide_dismissed}
        elif path == '/auth/workspace-guide' and route.request.method == 'PUT':
            guide_dismissed.append(True)
            route.fulfill(status=204)
            return
        elif path == '/billing/status':
            data = {'student_kind': 'institution', 'premium_access': True}
        elif path == '/enterprise/notifications':
            data = {'items': [], 'unread': 2}
        elif path == '/intelligence/student/actions':
            data = {'actions': []}
        elif path == '/students/dashboard':
            data = {'profile_completion': 0, 'applications': 0}
        elif path == '/enterprise/incidents' and route.request.method == 'POST':
            submitted.append(route.request.post_data_json)
            route.fulfill(status=201, json={'id': 'case-test', 'status': 'open'})
            return
        elif path in {'/students/jobs', '/students/applications', '/enterprise/custom-fields',
                      '/enterprise/announcements', '/enterprise/incidents'}:
            data = []
        route.fulfill(json=data)

    for prefix in ('auth', 'billing', 'students', 'intelligence', 'enterprise', 'ai'):
        page.route(f'**/{prefix}/**', respond)
    page.goto(BASE_URL, wait_until='networkidle')
    signed_in = True
    page.evaluate("() => window.PlaceAIAuth.completeSignIn({access_token:'synthetic-fixture-token'})")
    tour = page.locator('.workspace-tour-card')
    tour.get_by_role('heading', name='Dashboard', exact=True).wait_for()
    tour.get_by_role('button', name='Next').click()
    assert tour.get_by_role('heading', name='Opportunities', exact=True).is_visible()
    tour.get_by_role('button', name='Open section').click()
    page.locator('#app-nav [data-view=opportunities].active').wait_for(state='attached')
    with page.expect_response('**/auth/workspace-guide') as dismissed:
        tour.get_by_role('button', name='Skip tour').click()
    assert dismissed.value.status == 204
    assert tour.count() == 0
    assert page.get_by_role('button', name='Workspace tour', exact=True).count() == 0
    page.evaluate("localStorage.removeItem('placeai.workspace-tour.v1.guidance-test')")
    page.evaluate("() => window.PlaceAIAuth.completeSignIn({access_token:'synthetic-fixture-token'})")
    assert tour.count() == 0
    assert page.locator('#app-nav [data-view="announcements"], #app-nav [data-view="notifications"]').count() == 0
    assert page.locator('#notification-count').is_visible()
    page.get_by_role('button', name='Announcements', exact=True).click()
    page.get_by_role('heading', name='Placement announcements', exact=True).wait_for()
    page.get_by_role('button', name='Notifications', exact=True).click()
    page.get_by_role('heading', name='Notification centre', exact=True).wait_for()
    assert page.locator('#app-nav [data-view="calendar"]').evaluate(
        'el => {let prev=el.previousElementSibling;while(prev&&!prev.matches(".nav-group-label"))prev=prev.previousElementSibling;return prev.textContent}'
    ) == 'Campus'

    report = page.locator('#workspace-issue-panel')
    launch = page.get_by_role('button', name='Report an issue', exact=True)
    launch.click()
    report.get_by_label('Describe what happened').fill('Test draft stays in the drawer.')
    report.get_by_role('button', name='Minimize issue report').click()
    assert report.is_hidden()
    assert launch.get_attribute('aria-expanded') == 'false'
    launch.click()
    assert report.get_by_label('Describe what happened').input_value() == 'Test draft stays in the drawer.'
    report.get_by_role('button', name='Submit report').click()
    report.get_by_text('Report submitted.', exact=False).wait_for()
    assert submitted == [{'category': 'suspicious recruiter', 'description': 'Test draft stays in the drawer.', 'confidential': True}]
    report.get_by_role('button', name='View my reports').click()
    page.get_by_role('heading', name='Confidential incident reporting', exact=True).wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.close()
