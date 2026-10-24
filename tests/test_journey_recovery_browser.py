import json
from pathlib import Path

from playwright.sync_api import expect
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.technical_practice import TechnicalPracticeAttempt
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


def test_technical_exam_save_reload_submit_and_report(browser, layout_accounts, local_server):
    context = signed_context(browser, layout_accounts)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE_URL + '/?view=technical-practice', wait_until='networkidle')
    page.get_by_role('button', name='Begin technical exam', exact=True).click()
    expect(page.get_by_role('heading', name='Question 1 of 16', exact=True)).to_be_visible()
    page.locator('[name=technical-answer]').nth(0).check()
    expect(page.locator('#technical-notice')).to_have_text('Answer saved.')
    page.reload(wait_until='networkidle')
    page.locator('[data-technical-open]').first.click()
    expect(page.locator('[name=technical-answer]').nth(0)).to_be_checked()
    engine = create_engine('sqlite:///' + str(local_server))
    with Session(engine) as db:
        row = db.query(TechnicalPracticeAttempt).one()
        issued = json.loads(row.questions_json)
    for i, question in enumerate(issued):
        page.locator(f'[data-technical-question="{i}"]').click()
        option = page.locator('[name=technical-answer]').nth(question['correct'])
        if not option.is_checked():
            option.check()
            expect(page.locator('#technical-notice')).to_have_text('Answer saved.')
    for width in (1440, 768, 390, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
    page.set_viewport_size({'width': 1440, 'height': 1000})
    out = Path('../../outputs/placeai-journeys-20261024');out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / 'local-technical-exam.png'), full_page=True)
    page.get_by_role('button', name='Finish and review', exact=True).click()
    expect(page.get_by_role('heading', name='100% · 16 of 16 correct', exact=True)).to_be_visible()
    assert page.locator('.technical-review').count() == 16
    page.locator('.technical-review summary').first.click()
    expect(page.locator('.technical-review').first).to_contain_text('Correct answer:')
    page.screenshot(path=str(out / 'local-technical-report.png'), full_page=True)
    page.reload(wait_until='networkidle')
    page.locator('[data-technical-open]').first.click()
    expect(page.get_by_role('heading', name='100% · 16 of 16 correct', exact=True)).to_be_visible()
    assert not errors, errors
    engine.dispose();context.close()
