"""Email ownership and opt-in authenticator MFA; all enforcement lives server-side."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.email_delivery import send_transactional_email
from app.models import AccountProtection, RefreshSession, User
from app.rate_limit import enforce_auth_limits, enforce_rate_limit
from app.utils import hash_reset_token, verify_password

router = APIRouter(prefix="/auth", tags=["Account protection"])


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def protection(db: Session, user: User, *, lock: bool = False, request: Request | None = None) -> AccountProtection:
    if lock:
        # Use one lock order for password reset/logout and all factor operations.
        locked_user = db.query(User).filter_by(id=user.id).populate_existing().with_for_update().first()
        expected = getattr(request.state, "placeai_auth_version", None) if request else None
        if not locked_user or not locked_user.is_active or (expected is not None and expected != int(locked_user.auth_version or 1)):
            raise HTTPException(401, "Account session changed. Sign in again.")
    query = db.query(AccountProtection).filter_by(user_id=user.id)
    row = query.populate_existing().with_for_update().first() if lock else query.first()
    if row is None:
        row = AccountProtection(user_id=user.id)
        db.add(row)
        db.flush()
    return row


def cipher() -> Fernet:
    # Domain-separated key. Rotation of the signing secret needs an MFA key migration.
    key = hmac.new(get_settings().jwt_secret_key.encode(), b"PlaceAI/MFA/encryption/v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(user_id: str, secret: str) -> str:
    return cipher().encrypt(f"{user_id}|{secret}".encode()).decode()


def decrypt_secret(user_id: str, value: str) -> str:
    try:
        identity, secret = cipher().decrypt(value.encode()).decode().split("|", 1)
        if not hmac.compare_digest(identity, user_id):
            raise ValueError("MFA binding")
        return secret
    except (InvalidToken, ValueError):
        raise HTTPException(503, "Authenticator configuration is unavailable. Contact support.") from None


def totp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return f"{value % 1_000_000:06d}"


def consume_factor(row: AccountProtection, code: str, *, pending: bool = False) -> None:
    encrypted = row.mfa_pending if pending else row.mfa_secret
    if not encrypted:
        raise HTTPException(400, "Authenticator is not configured")
    secret = decrypt_secret(row.user_id, encrypted)
    current = int(time.time()) // 30
    if len(code) == 6 and code.isascii() and code.isdigit():
        for counter in (current - 1, current, current + 1):
            if counter > (row.mfa_last_counter if row.mfa_last_counter is not None else -1) and hmac.compare_digest(totp(secret, counter), code):
                row.mfa_last_counter = counter
                return
    if not pending:
        hashes = json.loads(row.recovery_hashes or "[]")
        digest = hash_reset_token(code.replace("-", "").upper())
        for index, stored in enumerate(hashes):
            if hmac.compare_digest(digest, stored):
                row.recovery_hashes = json.dumps(hashes[:index] + hashes[index + 1:])
                return
    raise HTTPException(401, "Invalid or already used authenticator code")


def login_challenge(user: User, db: Session) -> dict | None:
    row = db.get(AccountProtection, user.id)
    if not row or not row.mfa_secret:
        return None
    token = secrets.token_urlsafe(36)
    row.challenge_hash = hash_reset_token(token)
    row.challenge_expires = now() + timedelta(minutes=5)
    row.challenge_version = int(user.auth_version or 1)
    db.commit()
    return {"mfa_required": True, "mfa_challenge": token, "expires_in": 300}


def revoke_sessions(db: Session, user: User) -> None:
    user.auth_version = int(user.auth_version or 1) + 1
    db.query(RefreshSession).filter_by(user_id=user.id).filter(RefreshSession.revoked_at.is_(None)).update(
        {RefreshSession.revoked_at: now()}, synchronize_session=False)
    row = db.get(AccountProtection, user.id)
    if row:
        row.challenge_hash = None
        row.challenge_expires = None


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class EmailInput(BaseModel):
    email: EmailStr


def deliver_verification(sessions, email: str) -> tuple[str, str | None]:
    """Owner explicitly approved verified-email registration on 14 October 2026.

    Run after a generic registration/resend response, without disclosing existence.
    """
    with sessions() as db:
        user = db.query(User).filter_by(email=email.lower(), is_active=True).with_for_update().first()
        if not user or user.email_verified:
            return "skipped", None
        row = protection(db, user, lock=True)
        previous_hash, previous_expiry = row.email_token_hash, row.email_token_expires
        token = secrets.token_urlsafe(36)
        digest = hash_reset_token(token)
        row.email_token_hash, row.email_token_expires = digest, now() + timedelta(minutes=15)
        user_id = user.id
        db.commit()
    settings = get_settings()
    outcome, reason = send_transactional_email(settings, recipient=email,
        subject="Verify your PlaceAI email",
        body=f"Verify your email using this one-time link (expires in 15 minutes):\n\n{settings.base_url}/?verify_email_token={token}\n\nIf you did not request this, ignore this email.")
    if outcome != "sent":
        with sessions() as db:
            db.query(AccountProtection).filter_by(user_id=user_id, email_token_hash=digest).update(
                {AccountProtection.email_token_hash: previous_hash, AccountProtection.email_token_expires: previous_expiry},
                synchronize_session=False)
            db.commit()
    return outcome, reason


@router.post("/email-verification/resend", status_code=202)
def resend_verification(body: EmailInput, request: Request, background_tasks: BackgroundTasks,
                        db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="verify-email-send", identifier=str(body.email).lower(), limit=3,
                        window_seconds=900, block_seconds=300)
    background_tasks.add_task(deliver_verification, sessionmaker(bind=db.get_bind()), str(body.email).lower())
    return {"message": "If the account needs verification, a link will be sent. Check your inbox and spam folder."}


class PasswordInput(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class CodeInput(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class DisableInput(PasswordInput, CodeInput):
    pass


class ChallengeInput(CodeInput):
    challenge: str = Field(min_length=20, max_length=512)


@router.get("/security-status")
def security_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AccountProtection, user.id)
    return {"email_verified": bool(user.email_verified), "verification_required": bool(row and row.verification_required),
            "mfa_enabled": bool(row and row.mfa_secret), "mfa_recommended": user.role.value.endswith("admin")}


@router.post("/email-verification/request")
def request_verification(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="verify-email-send", identifier=user.id, limit=3,
                        window_seconds=900, block_seconds=300)
    if user.email_verified:
        return {"message": "Email is already verified."}
    outcome, _ = deliver_verification(sessionmaker(bind=db.get_bind()), user.email)
    if outcome != "sent":
        raise HTTPException(503, "Verification email is temporarily unavailable. Please try again.")
    return {"message": "Check your email for a verification link. It expires in 15 minutes."}


@router.post("/email-verification/confirm")
def confirm_verification(body: TokenInput, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="verify-email-confirm", limit=15, window_seconds=900, block_seconds=300)
    digest = hash_reset_token(body.token)
    candidate = db.query(AccountProtection.user_id).filter_by(email_token_hash=digest).first()
    if not candidate:
        raise HTTPException(400, "Invalid or expired verification link")
    user = db.query(User).filter_by(id=candidate.user_id).populate_existing().with_for_update().first()
    row = db.query(AccountProtection).filter_by(user_id=candidate.user_id, email_token_hash=digest).populate_existing().with_for_update().first()
    if not row or not row.email_token_expires or row.email_token_expires <= now():
        raise HTTPException(400, "Invalid or expired verification link")
    if not user or not user.is_active:
        raise HTTPException(400, "Invalid or expired verification link")
    user.email_verified = True
    row.verification_required = False
    row.email_token_hash = None
    row.email_token_expires = None
    db.commit()
    return {"message": "Email verified. You can now continue to your workspace."}


def reauthenticate(db: Session, request: Request, user: User, password: str) -> None:
    enforce_auth_limits(db, request, scope="mfa-manage", identifier=user.id, limit=6,
                        window_seconds=900, block_seconds=300)
    protection(db, user, lock=True, request=request)
    if not verify_password(password, user.hashed_password):
        raise HTTPException(401, "Current password is incorrect")


@router.post("/mfa/enroll")
def enroll(body: PasswordInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reauthenticate(db, request, user, body.password)
    row = protection(db, user, lock=True, request=request)
    if row.mfa_secret:
        raise HTTPException(409, "Authenticator is already enabled")
    if not user.email_verified:
        raise HTTPException(403, "Verify your email before enabling an authenticator")
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    row.mfa_pending = encrypt_secret(user.id, secret)
    row.mfa_pending_expires = now() + timedelta(minutes=10)
    db.commit()
    uri = f"otpauth://totp/{quote('PlaceAI:' + user.email, safe='')}?secret={secret}&issuer=PlaceAI&algorithm=SHA1&digits=6&period=30"
    return {"secret": secret, "otpauth_uri": uri, "expires_in": 600}


@router.post("/mfa/confirm")
def confirm_mfa(body: CodeInput, request: Request, response: Response,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="mfa-confirm", identifier=user.id, limit=6, window_seconds=900, block_seconds=300)
    row = protection(db, user, lock=True, request=request)
    if row.mfa_secret or not row.mfa_pending_expires or row.mfa_pending_expires <= now():
        raise HTTPException(400, "Authenticator setup has expired or is already completed")
    consume_factor(row, body.code, pending=True)
    row.mfa_secret, row.mfa_pending, row.mfa_pending_expires = row.mfa_pending, None, None
    codes = [secrets.token_hex(16).upper() for _ in range(8)]
    row.recovery_hashes = json.dumps([hash_reset_token(code) for code in codes])
    revoke_sessions(db, user)
    from app.routers.auth import _token_response
    tokens = _token_response(user, response, db, mfa_verified=True)
    return {**tokens.model_dump(), "recovery_codes": codes, "message": "Authenticator enabled. Save these one-time recovery codes offline."}


@router.post("/mfa/verify")
def verify_mfa(body: ChallengeInput, request: Request, response: Response,
               background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    digest = hash_reset_token(body.challenge)
    enforce_auth_limits(db, request, scope="mfa-login", identifier=digest, limit=6, window_seconds=300, block_seconds=300)
    candidate = db.query(AccountProtection.user_id).filter_by(challenge_hash=digest).first()
    if not candidate:
        raise HTTPException(401, "Sign-in challenge expired. Sign in again.")
    # A new password-authenticated challenge must not reset the account OTP budget.
    enforce_auth_limits(db, request, scope="mfa-account", identifier=candidate.user_id,
                        limit=6, window_seconds=300, block_seconds=300)
    user = db.query(User).filter_by(id=candidate.user_id).populate_existing().with_for_update().first()
    row = db.query(AccountProtection).filter_by(user_id=candidate.user_id, challenge_hash=digest).populate_existing().with_for_update().first()
    if not row or not row.challenge_expires or row.challenge_expires <= now():
        raise HTTPException(401, "Sign-in challenge expired. Sign in again.")
    if not user or not user.is_active or row.challenge_version != int(user.auth_version or 1):
        raise HTTPException(401, "Sign-in challenge expired. Sign in again.")
    consume_factor(row, body.code)
    row.challenge_hash, row.challenge_expires = None, None
    from app.routers.auth import _token_response
    tokens = _token_response(user, response, db, mfa_verified=True)
    from app.routers.access import CONTROLLED_LOGIN_ROLES, ROLE_LABELS, _deliver_controlled_login, _platform_admin_recipients, _record_login_activity
    _record_login_activity(db, user)
    db.commit()
    if user.role in CONTROLLED_LOGIN_ROLES:
        background_tasks.add_task(_deliver_controlled_login, {
            "role": ROLE_LABELS[user.role.value], "email": user.email,
            "signed_in_at": user.last_login_at.isoformat(timespec="seconds") + "Z",
        }, _platform_admin_recipients(db))
    return tokens


@router.post("/mfa/disable")
def disable_mfa(body: DisableInput, request: Request, response: Response,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reauthenticate(db, request, user, body.password)
    row = protection(db, user, lock=True, request=request)
    consume_factor(row, body.code)
    row.mfa_secret, row.mfa_pending, row.mfa_pending_expires = None, None, None
    row.recovery_hashes, row.mfa_last_counter = "[]", -1
    revoke_sessions(db, user)
    from app.routers.auth import _token_response
    return _token_response(user, response, db, mfa_verified=True)
