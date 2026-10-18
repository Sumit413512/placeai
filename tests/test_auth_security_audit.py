"""Adversarial authentication tests use only synthetic accounts and an isolated DB."""
from datetime import timedelta
import hashlib
import importlib
import json

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import auth_protection as protection, password_security, rate_limit
from app.database import Base, get_db
from app.dependencies import get_current_user, require_platform_admin
from app.models import AccountProtection, User, UserRole
from app.routers import auth, access, account_security_secure
from app.schemas import UserAuth
from app.utils import create_access_token, get_hashed_password, hash_reset_token

PASSWORD = "Synthetic audit credential 2026!"


@pytest.mark.parametrize('timestamp,expected',[(59,'287082'),(1111111109,'081804'),(1111111111,'050471'),(1234567890,'005924'),(2000000000,'279037'),(20000000000,'353130')])
def test_totp_matches_rfc6238_sha1_vectors(timestamp,expected):
    import base64
    secret=base64.b32encode(b'12345678901234567890').decode()
    assert protection.totp(secret,timestamp//30)==expected


@pytest.fixture
def secured(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(User(id="audit-user", email="audit@example.com", username="audit-user", role=UserRole.student,
                    email_verified=True, hashed_password=get_hashed_password(PASSWORD, check_breach=False)))
        db.commit()
    api = FastAPI()
    api.include_router(auth.router)
    api.include_router(protection.router)
    api.include_router(account_security_secure.router)
    api.include_router(access.router)
    @api.get('/private')
    def private(user=Depends(get_current_user)):
        return {"id":user.id}
    @api.get('/admin')
    def admin(user=Depends(require_platform_admin)):
        return {"id":user.id}
    def database():
        with sessions() as db:
            yield db
    api.dependency_overrides[get_db] = database
    monkeypatch.setattr(auth.settings, "environment", "test")
    with TestClient(api, base_url="https://audit.test") as client:
        yield client, sessions
    engine.dispose()


def login(client, path="/auth/login-json"):
    body = {"email":"audit@example.com", "password":PASSWORD}
    if path.endswith('login-role'):
        body['role'] = 'student'
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token):
    return {"Authorization":f"Bearer {token}"}


def test_logout_revokes_copied_access_and_all_refresh_credentials(secured):
    client, _ = secured
    first = login(client)
    second = login(client)
    assert client.post('/auth/logout').status_code == 204
    for tokens in (first, second):
        assert client.get('/private', headers=bearer(tokens['access_token'])).status_code == 401
        assert client.post('/auth/refresh', json={"refresh_token":tokens['refresh_token']}).status_code == 401


def test_api_bearer_logout_and_forged_logout(secured):
    client, _ = secured
    token = login(client)['access_token']
    client.cookies.clear()
    assert client.post('/auth/logout', headers=bearer(token+'x')).status_code == 204
    assert client.get('/private', headers=bearer(token)).status_code == 200
    assert client.post('/auth/logout', headers=bearer(token)).status_code == 204
    assert client.get('/private', headers=bearer(token)).status_code == 401


def test_roles_and_token_payload_cannot_grant_admin_access(secured):
    client, _ = secured
    token = login(client)['access_token']
    assert client.get('/admin', headers={**bearer(token),'Cookie':'role=platform_admin'}).status_code == 403
    h,p,s = token.split('.')
    import base64
    claims = json.loads(base64.urlsafe_b64decode(p+'='*(-len(p)%4)))
    claims['sub'] = 'administrator@example.com'
    forged = h+'.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.'+s
    assert client.get('/admin', headers=bearer(forged)).status_code == 401
    assert client.get('/private', headers=bearer('not-a-token')).status_code == 401


def test_new_public_accounts_must_verify_in_production_without_locking_legacy_accounts(secured, monkeypatch):
    client, sessions = secured
    monkeypatch.setattr(auth.settings,'environment','production')
    monkeypatch.setattr(password_security,'_range',lambda prefix: ('0'*35+':0',))
    captured = []
    monkeypatch.setattr(protection,'send_transactional_email',lambda *args,**kwargs: (captured.append(kwargs['body']) or 'sent',None))
    created = client.post('/auth/signup',json={'email':'new@example.com','username':'new-user','password':PASSWORD})
    assert created.status_code == 202,created.text
    assert 'access_token' not in created.json() and 'set-cookie' not in created.headers
    assert client.post('/auth/login-json',json={'email':'new@example.com','password':PASSWORD}).status_code == 401
    token = create_access_token('new@example.com',1)
    assert client.get('/private',headers=bearer(token)).status_code == 403
    assert client.get('/auth/me',headers=bearer(token)).status_code == 200
    reset_token = captured[0].split('verify_email_token=')[1].split()[0]
    with sessions() as db:
        row = db.query(AccountProtection).filter(AccountProtection.email_token_hash.is_not(None)).one()
        assert row.email_token_hash != reset_token
        assert row.email_token_expires < protection.now()+timedelta(minutes=16)
    assert client.post('/auth/email-verification/confirm',json={'token':reset_token}).status_code == 200
    assert client.post('/auth/email-verification/confirm',json={'token':reset_token}).status_code == 400
    signed_in = client.post('/auth/login-json',json={'email':'new@example.com','password':PASSWORD})
    assert signed_in.status_code == 200
    assert signed_in.json()['refresh_token'] is None
    cookie=signed_in.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie and 'Path=/auth' in cookie
    assert client.get('/private',headers=bearer(signed_in.json()['access_token'])).status_code == 200
    assert client.get('/private',headers=bearer(login(client)['access_token'])).status_code == 200



def test_verification_expiration_and_delivery_failures(secured, monkeypatch):
    client,sessions = secured
    token=login(client)['access_token']
    with sessions() as db:
        user=db.get(User,'audit-user'); user.email_verified=False
        db.add(AccountProtection(user_id=user.id,verification_required=True,email_token_hash=hash_reset_token('x'*36),email_token_expires=protection.now()-timedelta(seconds=1)))
        db.commit()
    assert client.post('/auth/email-verification/confirm',json={'token':'x'*36}).status_code == 400
    monkeypatch.setattr(protection,'send_transactional_email',lambda *a,**kw: ('failed','unavailable'))
    assert client.post('/auth/email-verification/request',headers=bearer(token)).status_code == 503
    assert client.get('/private',headers=bearer(token)).status_code == 403


def test_production_registration_and_resend_do_not_disclose_existing_accounts(secured,monkeypatch):
    client,sessions=secured
    monkeypatch.setattr(auth.settings,'environment','production')
    monkeypatch.setattr(password_security,'_range',lambda prefix: ('0'*35+':0',))
    monkeypatch.setattr(protection,'send_transactional_email',lambda *a,**kw: ('sent',None))
    existing=client.post('/auth/signup',json={'email':'audit@example.com','username':'audit-user','password':PASSWORD})
    missing=client.post('/auth/signup',json={'email':'other@example.com','username':'other-user','password':PASSWORD})
    duplicate_name=client.post('/auth/signup',json={'email':'not-created@example.com','username':'audit-user','password':PASSWORD})
    assert existing.status_code==missing.status_code==duplicate_name.status_code==202
    assert existing.json()==missing.json()==duplicate_name.json()
    known=client.post('/auth/email-verification/resend',json={'email':'audit@example.com'})
    unknown=client.post('/auth/email-verification/resend',json={'email':'missing@example.com'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    with sessions() as db:
        assert db.query(User).filter_by(email='audit@example.com').one().email_verified is True


def enroll(client,token):
    setup=client.post('/auth/mfa/enroll',headers=bearer(token),json={'password':PASSWORD})
    assert setup.status_code == 200,setup.text
    return setup.json()['secret']


def test_mfa_full_lifecycle_replay_recovery_and_all_login_paths(secured,monkeypatch):
    client,sessions = secured
    clock=[1800000000]
    monkeypatch.setattr(protection.time,'time',lambda: clock[0])
    old=login(client)['access_token']
    secret=enroll(client,old)
    confirmed=client.post('/auth/mfa/confirm',headers=bearer(old),json={'code':protection.totp(secret,clock[0]//30)})
    assert confirmed.status_code == 200,confirmed.text
    codes=confirmed.json()['recovery_codes']
    assert len(codes)==8
    assert client.get('/private',headers=bearer(old)).status_code==401
    with sessions() as db:
        row=db.get(AccountProtection,'audit-user')
        assert secret not in row.mfa_secret
        assert codes[0] not in row.recovery_hashes
    client.cookies.clear()
    for path in ('/auth/login-json','/auth/login-role','/auth/login'):
        if path.endswith('/login'):
            response=client.post(path,data={'username':'audit@example.com','password':PASSWORD})
            result=response.json()
        else:
            result=login(client,path)
        assert result['mfa_required'] is True and result['access_token'] is None
        assert 'placeai_refresh' not in client.cookies
        challenge=result['mfa_challenge']
        assert client.post('/auth/mfa/verify',json={'challenge':challenge,'code':protection.totp(secret,clock[0]//30)}).status_code==401
        clock[0]+=30
        verify=client.post('/auth/mfa/verify',json={'challenge':challenge,'code':protection.totp(secret,clock[0]//30)})
        assert verify.status_code==200,verify.text
        assert client.post('/auth/mfa/verify',json={'challenge':challenge,'code':codes[0]}).status_code==401
        client.cookies.clear()
    # The deliberate invalid attempts above exhaust a real account OTP window.
    # Exercise recovery in a later limiter window without weakening production limits.
    monkeypatch.setattr(rate_limit,'_utcnow',lambda: protection.now()+timedelta(minutes=6))
    challenge=login(client)['mfa_challenge']
    recovered=client.post('/auth/mfa/verify',json={'challenge':challenge,'code':codes[0]})
    assert recovered.status_code==200
    challenge=login(client)['mfa_challenge']
    assert client.post('/auth/mfa/verify',json={'challenge':challenge,'code':codes[0]}).status_code==401
    access_token=recovered.json()['access_token']
    disabled=client.post('/auth/mfa/disable',headers=bearer(access_token),json={'password':PASSWORD,'code':codes[1]})
    assert disabled.status_code==200,disabled.text
    assert login(client)['mfa_required'] is False


def test_mfa_requires_password_and_expiring_one_time_challenge(secured,monkeypatch):
    client,sessions=secured
    token=login(client)['access_token']
    assert client.post('/auth/mfa/enroll',headers=bearer(token),json={'password':'wrong'}).status_code==401
    secret=enroll(client,token)
    confirmed=client.post('/auth/mfa/confirm',headers=bearer(token),json={'code':protection.totp(secret,int(protection.time.time())//30)})
    assert confirmed.status_code==200
    result=login(client)
    with sessions() as db:
        row=db.get(AccountProtection,'audit-user'); row.challenge_expires=protection.now()-timedelta(seconds=1); db.commit()
    assert client.post('/auth/mfa/verify',json={'challenge':result['mfa_challenge'],'code':'123456'}).status_code==401
    assert client.get('/auth/security-status',headers=bearer(confirmed.json()['access_token'])).json()['mfa_enabled'] is True


def test_changing_mfa_challenge_does_not_reset_otp_guessing_limit(secured):
    client,sessions=secured
    with sessions() as db:
        db.add(AccountProtection(user_id='audit-user',mfa_secret=protection.encrypt_secret('audit-user','JBSWY3DPEHPK3PXP')));db.commit()
    for _ in range(6):
        challenge=login(client)['mfa_challenge']
        response=client.post('/auth/mfa/verify',json={'challenge':challenge,'code':'invalid-code'})
        assert response.status_code==401
    challenge=login(client)['mfa_challenge']
    assert client.post('/auth/mfa/verify',json={'challenge':challenge,'code':'invalid-code'}).status_code==429


def test_rate_limits_survive_ip_rotation_and_account_spraying(secured):
    _,sessions=secured
    with sessions() as db:
        for index in range(3):
            request=Request({'type':'http','headers':[],'client':(f'192.0.2.{index}',1234)})
            rate_limit.enforce_auth_limits(db,request,scope='audit-login',identifier='victim@example.com',limit=3,window_seconds=600,block_seconds=300)
        with pytest.raises(Exception) as error:
            rate_limit.enforce_auth_limits(db,Request({'type':'http','headers':[],'client':('192.0.2.200',1234)}),scope='audit-login',identifier='victim@example.com',limit=3,window_seconds=600,block_seconds=300)
        assert error.value.status_code==429
        request=Request({'type':'http','headers':[],'client':('192.0.2.220',1234)})
        for index in range(60):
            rate_limit.enforce_auth_limits(db,request,scope='audit-spray',identifier=f'user{index}@example.com',limit=3,window_seconds=600,block_seconds=300)
        with pytest.raises(Exception) as error:
            rate_limit.enforce_auth_limits(db,request,scope='audit-spray',identifier='new@example.com',limit=3,window_seconds=600,block_seconds=300)
        assert error.value.status_code==429


def test_breached_password_k_anonymity_and_outage_policy(monkeypatch):
    monkeypatch.setattr(auth.settings,'environment','production')
    password='Known synthetic breached password 123!'
    digest=hashlib.sha1(password.encode(),usedforsecurity=False).hexdigest().upper()
    seen=[]
    monkeypatch.setattr(password_security,'_range',lambda prefix: (seen.append(prefix) or digest[5:]+':42',))
    with pytest.raises(Exception) as error:
        get_hashed_password(password)
    assert error.value.status_code==422
    assert seen==[digest[:5]] and len(seen[0])==5
    def unavailable(prefix):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(password_security,'_range',unavailable)
    with pytest.raises(Exception) as error:
        get_hashed_password(password)
    assert error.value.status_code==503
    # Strong passphrases need not contain every character class.
    assert UserAuth(email='phrase@example.com',username='phrase',password='a unique orchard beside the river').password


def test_protected_route_inventory_has_explicit_public_allowlist():
    application=importlib.import_module('app.app').app
    allowed={'/auth/signup','/auth/login','/auth/login-json','/auth/refresh','/auth/logout','/auth/google-config',
             '/auth/google','/auth/forgot-password','/auth/reset-password','/auth/login-role',
             '/auth/email-verification/confirm','/auth/email-verification/resend','/auth/mfa/verify','/public/access-requests','/ai/status','/telemetry/page-view','/health'}
    for path,methods in application.openapi()['paths'].items():
        for method,operation in methods.items():
            if method in {'get','post','put','patch','delete'} and path not in allowed:
                assert operation.get('security'),(method,path)


def test_claiming_a_college_code_does_not_grant_private_campus_access(secured):
    from app.models import Organization, StudentProfile
    from app.student_entitlements import student_access_status
    client,sessions=secured
    with sessions() as db:
        db.add(Organization(id='audit-college',name='Audit College',slug='audit-college',is_active=True)); db.commit()
    created=client.post('/auth/signup',json={'email':'claim@example.com','username':'claim-user','password':PASSWORD,'organization_slug':'audit-college'})
    assert created.status_code==201
    with sessions() as db:
        user=db.get(User,created.json()['id']); user.created_at=protection.now()-timedelta(days=10)
        profile=db.query(StudentProfile).filter_by(user_id=user.id).one()
        db.commit()
        assert student_access_status(user,db)['campus_access'] is False
        profile.is_verified=True; db.commit()
        assert student_access_status(user,db)['campus_access'] is True
        db.get(Organization,'audit-college').is_active=False; db.commit()
        assert student_access_status(user,db)['campus_access'] is False
