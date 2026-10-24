from pathlib import Path

from playwright.sync_api import expect
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Job, RecruiterProfile
from app.zensar_practice import JOB_ID, TITLE
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_page_layout_browser import layout_accounts  # noqa: F401
from test_zensar_practice import seed_sql


def test_zensar_is_an_existing_proctored_exam_not_a_separate_practice_page(browser,layout_accounts,local_server):
    engine=create_engine('sqlite:///'+str(local_server))
    with Session(engine) as db:
        recruiter=db.query(RecruiterProfile).one()
        recruiter.company_name='TechNova Solutions — Demo'
        db.add(Job(recruiter_id=recruiter.id,title='PlaceAI TechNova Demo Assessment',description='Fictional local demo',visibility='public'))
        db.commit();db.execute(text(seed_sql()));db.commit()
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    context.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    email,password=layout_accounts['student']
    assert context.request.post(BASE_URL+'/auth/login-json',data={'email':email,'password':password}).status==200
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('https://**/*',lambda route:route.abort())
    page.goto(BASE_URL+'/?view=technical-practice',wait_until='domcontentloaded')
    expect(page.get_by_role('heading',name='Your placement overview',exact=True)).to_be_visible()
    assert page.locator('#app-nav [data-view="technical-practice"]').count()==0
    page.locator('#app-nav [data-view="mock-interview"]').click()
    expect(page.locator('#setup-panel')).to_be_visible()
    expect(page.locator('#job-select')).to_contain_text(TITLE)
    expect(page.locator('#job-select')).to_contain_text('PlaceAI TechNova Demo Assessment')
    assert page.get_by_role('link',name='Open technical practice exam',exact=True).count()==0
    page.locator('#job-select').select_option(JOB_ID)
    with page.expect_response('**/mock-interview/start') as started:
        page.get_by_role('button',name='Continue to secure system check',exact=True).click()
    assert started.value.status==200,started.value.text()
    data=started.value.json()
    assert len(data['questions'])==50 and data['mode']=='assessment'
    expect(page.locator('#system-panel')).to_be_visible()
    expect(page.locator('#selected-assessment')).to_contain_text('Zensar')
    expect(page.locator('#selected-assessment')).to_be_visible()
    expect(page.locator('#interview-title')).to_contain_text('Zensar')
    expect(page.locator('#interview-context')).to_contain_text('proctored forward-only mode')
    expect(page.locator('#interview-context')).to_contain_text('Not an official Zensar')
    expect(page.locator('#start-assessment')).to_be_disabled()
    assert sum(q.get('response_mode')=='audio' for q in data['questions'])==8
    assert sum(q['answer_type']=='video' for q in data['questions'])==4
    assert sum(q['answer_type']=='code' for q in data['questions'])==2
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),width
    page.set_viewport_size({'width':1440,'height':1000})
    out=Path('../../outputs/placeai-zensar-20261024');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'local-zensar-system-check.png'),full_page=True)
    assert not errors,errors
    context.close();engine.dispose()
