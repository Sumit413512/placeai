"""Real browser -> signed provider token -> real auth/database -> workspace.

Only Google's button and public certificate transport are replaced in the
isolated test server. Token signature/audience/nonce verification, provisioning,
MFA, cookies, refresh, student tools and logout use production code.
"""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8766"
RUNNER = '''
import json, time
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from google.auth import jwt
from google.auth.crypt import RSASigner
from google.auth.transport import requests
from app.app import app
from app.config import get_settings

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
signer = RSASigner.from_string(pem, key_id='isolated-test-key')
class Certificates:
    def __call__(self, url, method='GET', **kwargs):
        assert url == 'https://www.googleapis.com/oauth2/v1/certs'
        return SimpleNamespace(status=200, data=json.dumps({'isolated-test-key':public}).encode())
requests.Request = Certificates

@app.get('/__test_google/token')
def token(nonce: str, invalid: bool = False):
    claims = {'iss':'https://accounts.google.com','aud':get_settings().google_client_id,
              'iat':int(time.time()),'exp':int(time.time())+300,'sub':'isolated-browser-student',
              'email':'browser.new.student@gmail.com','email_verified':True,'name':'Browser Student','nonce':nonce}
    value = jwt.encode(signer, claims).decode()
    return {'credential':value + ('invalid' if invalid else '')}
'''

GOOGLE_BUTTON = '''
window.__googleInitializations = 0;
window.google = {accounts:{id:{
 initialize(config) { window.__googleInitializations++; window.__testGoogle = config; },
 renderButton(area, options) {
   const button = document.createElement('button'); button.type = 'button';
   button.textContent = 'Continue with Google';
   button.onclick = async () => {
     options.click_listener?.();
     const config = window.__testGoogle;
     const result = await fetch('/__test_google/token?nonce='+encodeURIComponent(config.nonce)+'&invalid='+Boolean(window.__invalidGoogle)).then(r=>r.json());
     config.callback(result);
   };
   area.append(button);
 }
}}};
'''


@pytest.fixture(scope="module")
def google_server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("google-browser")
    runner = directory / "google_test_server.py"
    runner.write_text(RUNNER, encoding="utf-8")
    database = directory / "isolated.db"
    env = {**os.environ, "ENVIRONMENT":"development", "DATABASE_URL":f"sqlite:///{database}",
           "AUTO_CREATE_SCHEMA":"true", "GOOGLE_CLIENT_ID":"isolated-browser.apps.googleusercontent.com",
           "JWT_SECRET_KEY":"isolated-browser-google-access-secret-abcdefghijklmnopqrstuvwxyz",
           "JWT_REFRESH_SECRET_KEY":"isolated-browser-google-refresh-secret-abcdefghijklmnopqrstuvwxyz",
           "BASE_URL":URL, "ALLOWED_ORIGINS":URL, "STUDENT_UNIFIED_ACCESS":"true",
           "PYTHONPATH":str(ROOT)+os.pathsep+str(directory)}
    log_path = directory / 'server.log'
    log = log_path.open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable,"-m","uvicorn","google_test_server:app","--host","127.0.0.1","--port","8766"],
                               cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            try:
                if urlopen(URL+"/health",timeout=1).status == 200:
                    break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError("Isolated Google auth server did not start: " + log_path.read_text(encoding='utf-8')[-4000:])
        yield database
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


def test_google_first_signup_returning_signin_refresh_and_logout(google_server):
    with sync_playwright() as pw:
        executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
        browser = pw.chromium.launch(headless=True, **({"executable_path":executable} if executable else {}))
        context = browser.new_context(viewport={"width":390,"height":844})
        context.add_init_script("localStorage.setItem('placeai.analytics.preference.v1','declined')")
        page = context.new_page()
        page.route("https://accounts.google.com/gsi/client",lambda route: route.fulfill(content_type="application/javascript",body=GOOGLE_BUTTON))
        errors = []
        page.on("pageerror",lambda error: errors.append(str(error)))
        page.goto(URL,wait_until="networkidle")
        assert page.evaluate("window.__googleInitializations || 0") == 0
        page.locator('.hero [data-open-auth=login]').click()
        page.get_by_role("button",name="Continue with Google",exact=True).wait_for()
        page.locator('[data-action=close-auth]').click()
        page.locator('.hero [data-open-auth=login]').click()
        assert page.evaluate("window.__googleInitializations") == 1
        # A real signature failure must remain visible; no reload or empty login.
        page.evaluate("window.__invalidGoogle=true")
        page.get_by_role("button",name="Continue with Google",exact=True).click()
        expect(page.locator('.google-sign-in [role=status]')).to_contain_text("could not be verified")
        assert page.locator('#auth-overlay').is_visible()
        with sqlite3.connect(google_server) as db:
            assert db.execute('select count(*) from users').fetchone()[0] == 0
        page.evaluate("window.__invalidGoogle=false")
        page.locator('#login-view [data-access-switch=create]').click()
        expect(page.locator('#auth-create-title')).to_have_text('Create your student account')
        # Google is independent of the email/password form and its constraints.
        page.locator('#role-student-signup-form [name=password]').fill('weak')
        page.get_by_role("button",name="Continue with Google",exact=True).click()
        choice = page.get_by_role("dialog",name="Add an extra layer of protection",exact=True)
        choice.get_by_role("button",name="Skip for now",exact=True).click()
        page.locator('#app-shell').wait_for(state="visible")
        page.locator('#auth-overlay').wait_for(state="hidden")
        with sqlite3.connect(google_server) as db:
            assert db.execute('select count(*) from users').fetchone()[0] == 1
            assert db.execute('select count(*) from student_profiles').fetchone()[0] == 1
            assert db.execute('select count(*) from google_identities').fetchone()[0] == 1
        page.set_viewport_size({"width":1440,"height":1000})
        views = page.locator('#app-nav [data-view]').evaluate_all('els=>els.map(el=>el.dataset.view)')
        assert {'drives','calendar','announcements','roadmap','learning-hub','mock-interview','resume','documents'} <= set(views)
        assert 'billing' not in views
        for view in ['readiness','roadmap','learning-hub','drives','calendar','announcements','documents']:
            nav = page.locator(f'#app-nav [data-view="{view}"]')
            if not nav.is_visible(): page.locator('.placeai-nav-more').click()
            nav.click()
            page.locator('#app-content .page-head').wait_for()
            assert not page.locator('#app-content').get_by_text('Unable to load this view',exact=True).count()
        page.reload(wait_until="networkidle")
        page.locator('#app-shell').wait_for(state="visible")
        assert page.evaluate("Object.values(sessionStorage).every(v=>!v.includes('eyJ'))")
        page.set_viewport_size({"width":390,"height":844})
        page.locator('.sidebar-trigger').click()
        page.locator('[data-action=logout]').first.click()
        page.locator('.hero [data-open-auth=login]').wait_for(state="visible")
        assert not any(c['name']=='placeai_refresh' for c in context.cookies())
        page.locator('.hero [data-open-auth=login]').click()
        # Password login failures also remain visible without navigation.
        form = page.locator('#role-login-form')
        form.locator('[name=email]').fill('browser.new.student@gmail.com')
        form.locator('[name=password]').fill('Incorrect local password 2026!')
        form.locator('button[type=submit]').click()
        expect(page.locator('#role-login-error')).to_contain_text('Incorrect email or password')
        page.get_by_role("button",name="Continue with Google",exact=True).click()
        choice.get_by_role("button",name="Skip for now",exact=True).click()
        page.locator('#app-shell').wait_for(state="visible")
        with sqlite3.connect(google_server) as db:
            assert db.execute('select count(*) from users').fetchone()[0] == 1
        assert not errors, errors
        browser.close()
