"""The verified sign-in handoff must retire every login overlay before slow workspace reads."""
import pytest
from playwright.sync_api import expect
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401

@pytest.mark.parametrize('role,label', [('student','Student'),('recruiter','Recruiter'),('institution_admin','Institution Admin'),('platform_admin','Platform Admin')])
def test_skipping_optional_authenticator_does_not_reveal_login_again(browser, role, label):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    logged=[False]; held=[]
    def api(route):
        path=route.request.url.split(BASE_URL)[-1].split('?')[0]
        if route.request.resource_type not in {'fetch','xhr'}:
            route.continue_(); return
        if path=='/auth/login-role': logged[0]=True; route.fulfill(json={'access_token':'isolated-token'}); return
        if path in {'/auth/me','/auth/refresh'} and not logged[0]: route.fulfill(status=401,json={'detail':'Sign in'}); return
        if path=='/auth/me': data={'id':'isolated-user','role':role,'username':'Isolated user','email':'test@example.invalid'}
        elif path=='/auth/refresh': data={'access_token':'isolated-token'}
        elif path=='/auth/security-status': data={'mfa_enabled':False,'email_verified':True}
        elif path=='/billing/status': data={'student_kind':'university','premium_access':True}
        elif path=='/enterprise/notifications' and not held: held.append(route); return
        elif path in {'/students/applications','/students/jobs'}: data=[]
        elif path=='/auth/google-config': data={'enabled':False}
        else: data={'items':[],'summary':{},'actions':[]}
        route.fulfill(json=data)
    page.route(BASE_URL+'/**', api)
    page.goto(BASE_URL,wait_until='networkidle')
    page.locator('.hero [data-open-auth="login"]').click()
    page.get_by_role('tab',name=label,exact=True).click()
    page.locator('#role-login-form input[name=email]').fill('test@example.invalid')
    page.locator('#role-login-form input[name=password]').fill('IsolatedTest2026!')
    page.locator('#role-login-form button[type=submit]').click()
    page.get_by_role('button',name='Skip for now',exact=True).click()
    # Do not wait for workspace APIs to finish: this was the visible stale-dialog window.
    expect(page.locator('#auth-overlay')).to_be_hidden(timeout=1000)
    expect(page.locator('.password-rotation-overlay')).to_have_count(0)
    expect(page.locator('#app-shell')).to_be_visible()
    page.wait_for_function('document.querySelector("#app-shell:not(.hidden)") !== null')
    assert held
    held[0].fulfill(json={'items':[],'unread':0})
    expect(page.locator('#app-content h1')).to_be_visible()
    expect(page.locator('#auth-overlay')).to_be_hidden()
    assert page.locator('.modal-overlay:not(.hidden), .password-rotation-overlay').count()==0
    page.reload(wait_until='networkidle')
    expect(page.locator('#app-shell')).to_be_visible()
    expect(page.locator('#auth-overlay')).to_be_hidden()
    page.close()
