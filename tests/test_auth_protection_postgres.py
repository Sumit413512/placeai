"""Real row-lock verification in an isolated schema; CI provisions PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException, Response
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth_protection import ChallengeInput, encrypt_secret, verify_mfa
from app.models import AccountProtection, AuditEvent, Organization, RateLimitBucket, RefreshSession, User, UserRole
from app.routers.auth import _token_response, refresh_token
from app.schemas import RefreshTokenRequest
from app.utils import hash_reset_token


def test_mfa_challenges_recovery_codes_and_refresh_rotate_once_under_concurrency():
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL service is required')
    engine=create_engine(url,pool_size=6,max_overflow=0)
    schema='auth_audit_'+uuid4().hex
    scoped=engine.execution_options(schema_translate_map={None:schema})
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        with scoped.begin() as connection:
            for model in (Organization,User,AccountProtection,AuditEvent,RateLimitBucket,RefreshSession):
                model.__table__.create(connection)
        with Session(scoped) as db:
            user=User(id='concurrent-user',email='concurrent@example.com',username='concurrent',
                      role=UserRole.student,hashed_password='unused-synthetic-hash',email_verified=True)
            db.add(user);db.flush()
            db.add(AccountProtection(user_id=user.id,mfa_secret=encrypt_secret(user.id,'JBSWY3DPEHPK3PXP'),
                recovery_hashes=json.dumps([hash_reset_token('A'*32),hash_reset_token('B'*32)])))
            db.commit()
            challenge=_token_response(user,Response(),db).mfa_challenge
        def attempt(_):
            request=Request({'type':'http','headers':[],'client':('192.0.2.3',1234)})
            with Session(scoped) as db:
                try:
                    result=verify_mfa(ChallengeInput(challenge=challenge,code='A'*32),request,Response(),BackgroundTasks(),db)
                    return 200,result.access_token
                except HTTPException as exc:
                    return exc.status_code,None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(attempt,range(4)))
        assert sorted(status for status,_ in results)==[200,401,401,401]
        with Session(scoped) as db:
            assert json.loads(db.get(AccountProtection,'concurrent-user').recovery_hashes)==[hash_reset_token('B'*32)]
            assert db.query(RefreshSession).count()==1
            original=db.query(RefreshSession).one()
            # Use a separately issued raw refresh credential for the actual handler.
            user=db.get(User,'concurrent-user')
            response=Response(); tokens=_token_response(user,response,db,mfa_verified=True)
            raw=tokens.refresh_token
            assert raw and original.revoked_at is None
        def rotate(_):
            with Session(scoped) as db:
                try:
                    refresh_token(RefreshTokenRequest(refresh_token=raw),Request({'type':'http','headers':[],'client':('192.0.2.4',1234)}),Response(),db)
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses=list(pool.map(rotate,range(4)))
        assert sorted(statuses)==[200,401,401,401]
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
