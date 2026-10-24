"""Actual local browser -> authenticated API -> isolated SQLite -> rendered progress."""
import json
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import expect
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import User,UserRole,StudentProfile,LearningNotebook
from app.roadmap_models import CareerRoadmap
from app.utils import get_hashed_password
from test_browser_smoke import BASE_URL,browser,local_server  # noqa: F401
from test_learning_hub import plan_data
from test_learning_standard import standard_chapter


def test_real_student_can_track_read_delete_restore_and_resume_notes(browser,local_server):
    engine=create_engine('sqlite:///'+str(local_server)); suffix=uuid4().hex[:10]
    email=f'study-{suffix}@example.com';password='IsolatedStudyTest2026!'
    with Session(engine) as db:
        user=User(email=email,username='study-'+suffix,hashed_password=get_hashed_password(password),role=UserRole.student,is_active=True,email_verified=True)
        db.add(user);db.flush();profile=StudentProfile(user_id=user.id,full_name='Study verification');db.add(profile);db.flush()
        plan=plan_data();plan['chapters']=plan['chapters'][:1]
        book=LearningNotebook(user_id=user.id,request_id='browser-'+suffix,title='SQL study verification',state='ready',
            input_json=json.dumps({'topic':'SQL','chapters':8}),plan_json=json.dumps(plan),chapters_json=json.dumps([standard_chapter()]),
            sources_json=json.dumps([{'title':'PostgreSQL','url':'https://www.postgresql.org/docs/current/'}]))
        roadmap=CareerRoadmap(student_id=profile.id,title='Data engineering roadmap',roadmap_json=json.dumps({'estimated_days':45,'weekly_hours':7,'phases':[{'name':'Foundations','outcomes':['Explain relational keys','Build a query pipeline']}]}))
        db.add_all([book,roadmap]);db.commit();book_id=book.id
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    page.goto(BASE_URL,wait_until='networkidle')
    page.locator('.hero [data-open-auth="login"]').click()
    page.locator('#role-login-form input[name=email]').fill(email)
    page.locator('#role-login-form input[name=password]').fill(password)
    with page.expect_response(lambda r:'/auth/login-role' in r.url) as login:
        page.locator('#role-login-form button[type=submit]').click()
    assert login.value.status==200,login.value.json().get('detail')
    page.get_by_role('button',name='Skip for now',exact=True).click()
    expect(page.locator('#auth-overlay')).to_be_hidden()
    page.locator('#app-nav [data-view="study-tracker"]').click()
    expect(page.get_by_role('heading',name='Make the next session count.',exact=True)).to_be_visible()
    page.get_by_label('Plan name',exact=True).fill('SQL preparation')
    page.get_by_role('button',name='Create study plan',exact=True).click()
    page.locator('.study-add-goal summary').click()
    page.locator('[data-study-goal-form] select[name=resource_id]').select_option(book_id)
    page.get_by_role('button',name='Add goal',exact=True).click()
    expect(page.locator('.study-goal')).to_contain_text('0 of 3 sections complete')
    page.get_by_role('button',name='Update PDF reading',exact=True).click()
    page.get_by_label('Finished through section').select_option('1.2')
    page.get_by_role('button',name='Mark through this section',exact=True).click()
    expect(page.locator('.study-goal')).to_contain_text('2 of 3 sections complete')
    expect(page.locator('.study-plan>.panel-head')).to_contain_text('66%')
    page.get_by_role('button',name='Continue',exact=True).click()
    expect(page.locator('.notes-focus-reader')).to_be_visible()
    expect(page.locator('.notes-focus-content h3')).to_contain_text('1.2')
    page.get_by_label('Reading text size').select_option('20')
    assert page.locator('.notes-focus-content p').first.evaluate('e=>getComputedStyle(e).fontSize')=='20px'
    expect(page.get_by_label('I have finished this section',exact=True)).to_be_checked()
    page.get_by_role('button',name='Next section',exact=True).click()
    page.get_by_label('I have finished this section',exact=True).check()
    expect(page.locator('[data-notes-progress]')).to_contain_text('100% marked complete')
    assert page.locator('.notes-focus-content').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
        assert page.locator('.notes-focus-content').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),width
    page.set_viewport_size({'width':1440,'height':1000})
    reader_out=Path('../../outputs/placeai-study-20261024');reader_out.mkdir(parents=True,exist_ok=True);page.locator('.notes-focus-reader').screenshot(path=str(reader_out/'local-notes-reader.png'))
    page.get_by_role('button',name='Back to notebook',exact=True).click()
    page.get_by_role('button',name='Delete notebook: SQL study verification',exact=True).click()
    page.get_by_role('button',name='Delete notebook',exact=True).click()
    expect(page.locator('#learning-library [data-learning-id]')).to_have_count(0)
    page.get_by_role('button',name='Deleted notes',exact=True).click()
    page.get_by_role('button',name='Restore',exact=True).click()
    expect(page.locator('#learning-library [data-learning-id]')).to_have_count(1)
    page.locator('#learning-library [data-learning-id]').click()
    expect(page.locator('[data-notes-progress]')).to_contain_text('100% marked complete')
    page.locator('#app-nav [data-view="study-tracker"]').click()
    expect(page.locator('.study-plan>.panel-head')).to_contain_text('100%')
    expect(page.get_by_role('button',name='Another reminder',exact=True)).to_have_count(0)
    text=page.locator('#study-reminder').inner_text()
    art=page.locator('.study-illustration').get_attribute('aria-label')
    page.locator('#app-nav [data-view="dashboard"]').click()
    page.locator('#app-nav [data-view="study-tracker"]').click()
    expect(page.locator('#study-reminder')).not_to_have_text(text)
    assert page.locator('.study-illustration').get_attribute('aria-label') != art
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    page.set_viewport_size({'width':1440,'height':1000})
    out=Path('../../outputs/placeai-study-20261024');out.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out/'local-study-tracker.png'),full_page=True)
    page.reload(wait_until='networkidle');expect(page.locator('.study-plan>.panel-head')).to_contain_text('100%')
    expect(page.locator('#auth-overlay')).to_be_hidden();page.close();engine.dispose()
