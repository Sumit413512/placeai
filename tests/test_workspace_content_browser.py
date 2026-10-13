import json
from pathlib import Path

import pytest

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


@pytest.mark.parametrize('width', [1440, 390])
def test_saved_roadmap_readability_structure_and_supplementary_notes(browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 960})
    saved = {
        'title': 'Data engineering plan', 'created_at': '2026-10-13T10:00:00Z',
        'estimated_days': 60, 'weekly_hours': 8,
        'input': {'target_roles': ['Data engineer'], 'current_skills': ['Python']},
        'market_snapshot': {'target_roles': ['Data engineer'], 'region': 'India',
                            'in_demand_skills': ['Python', 'SQL', 'Git', 'ETL'],
                            'demand_signals': ['SQL appeared in 24 of 36 listings.', 'Git appeared in 21 of 36 listings.'],
                            'market_notes': ['Public job feeds are a sample, not a hiring guarantee.']},
        'roadmap': {'phases': [{'phase': 1, 'name': 'SQL foundations', 'days': 14,
                               'outcomes': ['Write joins and aggregate queries.'],
                               'practice': ['Build and query a sample database.'],
                               'skills': [{'name': 'SQL', 'level': 'working', 'why': 'Query relational data.'}],
                               'projects': [], 'milestone': 'Explain and demonstrate a reporting query.'}],
                    'portfolio_plan': ['Build a documented data pipeline.'],
                    'interview_preparation': ['Explain indexes and query plans.'],
                    'advanced_next_steps': [], 'disclaimer': 'Review recommendations against your goals.'},
        'sources': [{'title': 'PostgreSQL documentation', 'url': 'https://www.postgresql.org/docs/'}],
    }

    def api_response(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        if path.startswith('/static/'):
            route.continue_()
            return
        if path == '/auth/me':
            data = {'id': 'readability-review', 'username': 'Review student', 'email': 'review@example.test', 'role': 'student'}
        elif path == '/roadmap/status':
            data = {'allowed': True, 'latest_available': True}
        elif path == '/roadmap/latest':
            data = saved
        elif path == '/enterprise/notifications':
            data = {'items': [], 'unread': 0}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/roadmap/**', '**/students/**', '**/enterprise/**', '**/billing/**', '**/ai/**', '**/intelligence/**'):
        page.route(pattern, api_response)
    page.goto(BASE_URL + '/?view=roadmap', wait_until='networkidle')
    signals = page.locator('.roadmap-market-panel > .check-list li')
    signals.first.wait_for()
    assert signals.count() == 2
    assert signals.first.evaluate('el => getComputedStyle(el).color') == 'rgb(39, 35, 48)'
    assert signals.first.evaluate('el => getComputedStyle(el).fontSize') == '16px'
    assert signals.first.evaluate('el => getComputedStyle(el).display') == 'list-item'
    assert page.locator('.roadmap-priority-grid > .panel').first.bounding_box()['height'] < 300
    assert page.locator('.roadmap-support-section').count() == 2
    assert page.get_by_role('heading', name='Advanced next steps', exact=True).count() == 0
    assert 'No additional items were returned' not in page.locator('#app-content').inner_text()
    assert page.locator('.roadmap-phase-stack .check-list li').first.evaluate('el => getComputedStyle(el).color') == 'rgb(39, 35, 48)'

    notes = page.locator('.roadmap-market-notes')
    summary = notes.locator('summary')
    assert notes.get_attribute('open') is None
    summary.press('Enter')
    assert notes.get_attribute('open') is not None
    assert notes.locator('li').is_visible()
    summary.press('Enter')
    assert notes.get_attribute('open') is None
    page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    assert notes.get_attribute('open') is not None
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    assert notes.get_attribute('open') is None

    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    output = Path(__file__).resolve().parents[1] / 'work/readable-content-review'
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'roadmap-{width}.png'), full_page=True)
    page.close()
