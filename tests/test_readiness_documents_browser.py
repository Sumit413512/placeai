import json
from pathlib import Path

import pytest

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


@pytest.mark.parametrize('width', [1440, 390])
def test_readiness_evidence_and_document_vault_accessibility(browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 960})
    labels = ['Profile completeness', 'Resume strength', 'Technical skills',
              'Role alignment', 'Interview readiness', 'Academic eligibility', 'Project evidence']

    def response(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        if path == '/auth/me':
            data = {'id': 'accessibility-review', 'username': 'Review student',
                    'email': 'review@example.test', 'role': 'student'}
        elif path == '/intelligence/student/readiness':
            data = {'score': 71, 'readiness_band': 'Building readiness',
                    'disclaimer': 'Evidence of preparation, not a hiring prediction.',
                    'evidence': [{'label': label, 'score': 55, 'confidence': 'medium',
                                  'source': 'Verified profile',
                                  'evidence': 'Build evidence through assessments and projects.'}
                                 for label in labels],
                    'next_best_action': {'title': 'Review your profile.', 'view': 'profile'}}
        elif path == '/enterprise/documents':
            data = []
        elif path == '/enterprise/notifications':
            data = {'items': [], 'unread': 0}
        elif path == '/billing/status':
            data = {'student_kind': 'institution', 'premium_access': True}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/students/**', '**/enterprise/**', '**/billing/**',
                    '**/ai/**', '**/intelligence/**'):
        page.route(pattern, response)
    page.goto(BASE_URL + '/?view=readiness', wait_until='networkidle')
    cards = page.locator('.readiness-component')
    cards.first.wait_for()
    assert cards.count() == 7
    assert page.locator('.readiness-score small').count() == 0
    assert page.get_by_role('heading', name='Building readiness', exact=True).count() == 1
    assert page.locator('.readiness-score').inner_text().split() == ['71', '/100']
    assert 'Profile completeness 55 / 100' in cards.first.inner_text().replace('\n', ' ')
    assert cards.first.locator('header').evaluate('el => getComputedStyle(el).display') == 'flex'
    assert cards.first.locator('strong').evaluate('el => getComputedStyle(el).fontSize') == '16px'
    assert cards.first.locator('p').evaluate('el => getComputedStyle(el).lineHeight') == '25.6px'
    grid = page.locator('.readiness-components').bounding_box()
    assert abs(cards.last.bounding_box()['width'] - grid['width']) < 2
    active = page.locator('#app-nav button[aria-current="page"]')
    assert active.count() == 1
    assert active.get_attribute('data-view') == 'readiness'
    assert active.evaluate("el => getComputedStyle(el, '::after').backgroundColor") == 'rgb(40, 89, 79)'
    assert page.locator('.ai-box-head').inner_text() == 'Evidence → action'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    output = Path(__file__).resolve().parents[1] / 'work/accessibility-review'
    output.mkdir(parents=True, exist_ok=True)
    metrics = page.locator('#app-shell').evaluate('''shell => {
      const nodes = [...shell.querySelectorAll('*')].filter(el =>
        el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' &&
        [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
      return {fontSizes: [...new Set(nodes.map(el => getComputedStyle(el).fontSize))],
              textColours: [...new Set(nodes.map(el => getComputedStyle(el).color))]};
    }''')
    (output / f'readiness-{width}-metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    page.screenshot(path=str(output / f'readiness-{width}.png'), full_page=True)

    page.goto(BASE_URL + '/?view=documents', wait_until='networkidle')
    page.get_by_role('heading', name='Vault is empty', level=2).wait_for()
    assert page.locator('#app-content h1').count() == 1
    assert page.locator('#app-content h3').count() == 0
    assert page.get_by_role('combobox', name='Document type').is_visible()
    assert page.get_by_role('button', name='Upload document').is_enabled()
    assert page.locator('#student-document-file').get_attribute('accept') == '.pdf,.png,.jpg,.jpeg'
    icon = page.locator('svg.command-launch-icon')
    assert icon.get_attribute('aria-hidden') == 'true'
    assert icon.evaluate('el => getComputedStyle(el).color') == 'rgb(23, 36, 59)'
    if width == 1440:
        page.get_by_role('button', name='Search PlaceAI', exact=True).click()
        page.locator('#command-search').wait_for(state='visible')
        page.keyboard.press('Escape')
        assert page.locator('#command-palette').is_hidden()
    overflow = page.evaluate('''() => [...document.querySelectorAll('#app-shell *')]
      .filter(el => el.getClientRects().length && el.getBoundingClientRect().right > innerWidth + 1)
      .map(el => ({tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width}))''')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), overflow
    page.close()


@pytest.mark.parametrize('width,score,band,text_scale', [
    (1440, 73, 'Building readiness', 1),
    (390, 100, 'Ready for interviews with verified preparation evidence', 1),
    (320, 0, 'No preparation evidence available yet', 2),
    (320, 100, 'Ready for interviews with verified preparation evidence', 2),
])
def test_readiness_score_stays_inside_circle_with_long_labels_and_large_text(browser, width, score, band, text_scale):
    page = browser.new_page(viewport={'width': width, 'height': 960})
    if text_scale != 1:
        page.add_init_script(f"document.addEventListener('DOMContentLoaded', () => document.documentElement.style.fontSize = '{text_scale * 100}%')")

    def response(route):
        path = route.request.url.split(BASE_URL, 1)[-1].split('?', 1)[0]
        if path == '/auth/me':
            data = {'id': 'score-review', 'username': 'Review student', 'role': 'student'}
        elif path == '/intelligence/student/readiness':
            data = {'score': score, 'readiness_band': band, 'evidence': [],
                    'disclaimer': 'Preparation evidence, not a hiring prediction.'}
        elif path == '/enterprise/notifications':
            data = {'items': [], 'unread': 0}
        else:
            data = {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    for pattern in ('**/auth/**', '**/students/**', '**/enterprise/**', '**/billing/**',
                    '**/ai/**', '**/intelligence/**'):
        page.route(pattern, response)
    page.goto(BASE_URL + '/?view=readiness', wait_until='networkidle')
    ring = page.locator('.readiness-score')
    ring.wait_for()
    assert ring.inner_text().split() == [str(score), '/100']
    assert page.get_by_role('heading', name=band, exact=True).count() == 1
    # A rectangular bounding box alone misses text crossing a circle's curved edge.
    assert ring.evaluate('''ring => {
      const box = ring.getBoundingClientRect(), style = getComputedStyle(ring);
      const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
      const radius = box.width / 2 - parseFloat(style.borderLeftWidth);
      return [...ring.children].every(el => {
        const b = el.getBoundingClientRect();
        return [[b.left,b.top],[b.right,b.top],[b.left,b.bottom],[b.right,b.bottom]]
          .every(([x,y]) => Math.hypot(x-cx,y-cy) <= radius + 1);
      });
    }''')
    hero = page.locator('.readiness-hero').bounding_box()
    label = page.get_by_role('heading', name=band, exact=True).bounding_box()
    assert label['x'] >= hero['x'] and label['x'] + label['width'] <= hero['x'] + hero['width'] + 1
    output = Path(__file__).resolve().parents[1] / 'work/score-fit-review'
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'readiness-{width}-{text_scale}x.png'), full_page=True)
    page.close()
