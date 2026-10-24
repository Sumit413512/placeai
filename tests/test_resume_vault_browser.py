"""Real local UI -> authenticated HTTP -> isolated DB, with student and staff sessions."""
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from playwright.sync_api import expect
from app.models import User, UserRole, StudentProfile, Organization
from app.utils import get_hashed_password
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401
from test_resume_evidence_vault import pdf_bytes


def sign_in(page,email,password,role='student'):
    page.goto(BASE_URL,wait_until='networkidle')
    page.locator('.hero [data-open-auth="login"]').click()
    page.locator(f'#login-view [data-access-role="{role}"]').click()
    page.locator('#role-login-form input[name=email]').fill(email)
    page.locator('#role-login-form input[name=password]').fill(password)
    page.locator('#role-login-form button[type=submit]').click()
    page.get_by_role('button',name='Skip for now',exact=True).click()
    expect(page.locator('#auth-overlay')).to_be_hidden()
    expect(page.locator('#app-shell')).to_be_visible()


def test_resume_review_and_consented_semester_documents(browser,local_server):
    engine=create_engine('sqlite:///'+str(local_server));suffix=uuid4().hex[:8]
    password='LocalEvidence2026!';email=f'evidence-{suffix}@example.com';admin_email=f'tpo-{suffix}@example.com'
    with Session(engine) as db:
        org=Organization(name='Evidence browser college',slug='evidence-'+suffix,is_active=True);db.add(org);db.flush()
        student=User(email=email,username='evidence-'+suffix,hashed_password=get_hashed_password(password),role=UserRole.student,email_verified=True,organization_id=org.id)
        admin=User(email=admin_email,username='tpo-'+suffix,hashed_password=get_hashed_password(password),role=UserRole.institution_admin,email_verified=True,organization_id=org.id)
        db.add_all([student,admin]);db.flush();db.add(StudentProfile(user_id=student.id,organization_id=org.id,full_name='Evidence browser student',degree='B.Tech',branch='Computer science',current_semester=4,is_verified=True));db.commit()
    context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page()
    page.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
    sign_in(page,email,password)
    page.goto(BASE_URL+'/?view=resume',wait_until='networkidle')
    raw=pdf_bytes(['Education: Bachelor of Engineering','Projects','Built Python pipelines for 100 records','Skills: Python, SQL'])
    page.locator('#resume-file').set_input_files({'name':'evidence-resume.pdf','mimeType':'application/pdf','buffer':raw})
    expect(page.locator('.resume-card')).to_contain_text('evidence-resume.pdf')
    page.get_by_label('Role template',exact=True).select_option('Data engineer')
    while page.locator('.evidence-requirement-row').count()>2:
        page.get_by_role('button',name='Remove requirement 3',exact=True).click()
    page.get_by_label('Requirement 1',exact=True).fill('Python')
    page.get_by_label('Requirement 2',exact=True).fill('Redis')
    page.get_by_label('Importance for requirement 2',exact=True).select_option('preferred')
    page.get_by_role('button',name='Save target checklist',exact=True).click()
    expect(page.get_by_label('Target role',exact=True)).to_have_value('Data engineer')
    page.get_by_role('button',name='Review resume',exact=True).click()
    expect(page.locator('.evidence-score-grid')).to_contain_text('66')
    expect(page.get_by_role('heading',name='Role checklist with proof')).to_be_visible()
    expect(page.locator('#resume-evidence-panel')).to_contain_text('Built Python pipelines for 100 records')
    assert page.locator('.evidence-status.not_found').count()==1
    output=Path('../../outputs/placeai-evidence-20261024');output.mkdir(parents=True,exist_ok=True)
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    page.set_viewport_size({'width':1440,'height':1000})
    page.screenshot(path=str(output/'local-resume-review.png'),full_page=True)
    page.reload(wait_until='networkidle')
    expect(page.locator('.evidence-score-grid')).to_contain_text('66')
    expect(page.locator('#auth-overlay')).to_be_hidden()
    page.goto(BASE_URL+'/?view=documents',wait_until='networkidle')
    page.get_by_label('Document semester',exact=True).fill('4')
    page.get_by_label('Label',exact=True).fill('Semester 4 marksheet')
    page.locator('#student-document-file').set_input_files({'name':'semester4.pdf','mimeType':'application/pdf','buffer':raw})
    page.get_by_role('button',name='Upload document',exact=True).click()
    expect(page.locator('.vault-document')).to_contain_text('Private')
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    page.set_viewport_size({'width':1440,'height':1000})
    staff_context=browser.new_context(viewport={'width':1440,'height':1000});staff=staff_context.new_page()
    sign_in(staff,admin_email,password,'institution_admin')
    staff.goto(BASE_URL+'/?view=documents',wait_until='networkidle')
    staff.get_by_label('Current semester',exact=True).fill('4')
    staff.get_by_label('Course',exact=True).fill('B.Tech')
    staff.get_by_role('button',name='Filter records',exact=True).click()
    staff.locator('.vault-student summary').click()
    expect(staff.locator('.vault-student')).to_contain_text('No documents submitted')
    page.locator('[data-vault-submit] input[type=checkbox]').check()
    page.get_by_role('button',name='Submit to institution',exact=True).click()
    expect(page.locator('.vault-document')).to_contain_text('Submitted to Evidence browser college')
    staff.get_by_role('button',name='Filter records',exact=True).click()
    staff.locator('.vault-student summary').click()
    expect(staff.locator('.vault-document')).to_contain_text('Semester 4 marksheet')
    with staff.expect_download() as download:
        with staff.expect_response(lambda r:'/documents/' in r.url and '/download' in r.url and r.status==200) as response:
            staff.get_by_role('button',name='Download',exact=True).click()
        assert response.value.status==200,response.value.text()
    assert Path(download.value.path()).read_bytes()==raw
    with staff.expect_popup() as preview:
        staff.get_by_role('button',name='View',exact=True).click()
    preview.value.wait_for_url('blob:**')
    preview.value.close()
    staff.screenshot(path=str(output/'local-institution-documents.png'),full_page=True)
    for width in (1440,768,390,320):
        staff.set_viewport_size({'width':width,'height':1000})
        assert staff.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    page.get_by_role('button',name='Withdraw submission',exact=True).click()
    expect(page.locator('.vault-document')).to_contain_text('Private')
    staff.get_by_role('button',name='Filter records',exact=True).click()
    staff.locator('.vault-student summary').click()
    expect(staff.locator('.vault-document')).to_have_count(0)
    context.close();staff_context.close();engine.dispose()
