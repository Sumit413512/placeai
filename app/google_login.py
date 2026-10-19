"""Google identity verification and account binding; never provisions privileged roles."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GoogleIdentity, RateLimitBucket, RecruiterProfile, StudentProfile, User, UserRole, utcnow
from app.rate_limit import enforce_auth_limits, enforce_rate_limit
from app.schemas import GoogleAuthRequest
from app.utils import get_hashed_password, verify_password

COOKIE = "placeai_google_nonce"
logger = logging.getLogger("placeai.google_login")


def challenge(response: Response, request: Request | None = None) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    settings = get_settings()
    if not settings.google_client_id:
        return {"enabled": False, "client_id": None}
    # Opening another sign-in panel/tab must not invalidate an active Google
    # popup by overwriting its double-submit cookie with a different nonce.
    if request:
        try:
            nonce, signature = request.cookies.get(COOKIE, "").rsplit(".", 1)
            expected = hmac.new(settings.jwt_secret_key.encode(), nonce.encode(), hashlib.sha256).hexdigest()
            age = time.time() - int(nonce.split(".", 1)[0])
            if hmac.compare_digest(signature, expected) and 0 <= age < 480:
                return {"enabled": True, "client_id": settings.google_client_id, "nonce": nonce,
                        "expires_in": max(0, int(600 - age))}
        except (ValueError, TypeError):
            pass
    nonce = f"{int(time.time())}.{secrets.token_urlsafe(32)}"
    signature = hmac.new(settings.jwt_secret_key.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    response.set_cookie(COOKIE, f"{nonce}.{signature}", max_age=600, httponly=True,
                        secure=settings.is_production, samesite="strict", path="/auth")
    return {"enabled": True, "client_id": settings.google_client_id, "nonce": nonce, "expires_in": 600}


def verify_credential(credential: str) -> dict:
    from google.auth.transport import requests
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(credential, requests.Request(), get_settings().google_client_id)


def authenticate(payload: GoogleAuthRequest, request: Request, response: Response, db: Session) -> User:
    settings = get_settings()
    enforce_rate_limit(db, request, scope="google-auth", limit=30, window_seconds=600, block_seconds=900)
    if not settings.google_client_id:
        raise HTTPException(503, "Google Sign-In is not configured")
    verification_step = "challenge"
    request.state.google_auth_step = verification_step
    try:
        nonce, signature = request.cookies.get(COOKIE, "").rsplit(".", 1)
        expected = hmac.new(settings.jwt_secret_key.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        age = time.time() - int(nonce.split(".", 1)[0])
        if not hmac.compare_digest(signature, expected) or not 0 <= age <= 600:
            raise ValueError("Invalid challenge")
        verification_step = "provider_identity"
        request.state.google_auth_step = verification_step
        info = verify_credential(payload.credential)
        verification_step = "nonce_binding"
        request.state.google_auth_step = verification_step
        if not hmac.compare_digest(str(info.get("nonce", "")), nonce):
            raise ValueError("Challenge mismatch")
    except Exception as exc:
        # Never log the credential, claims, email or upstream exception text.
        logger.warning("Google sign-in verification failed: %s", verification_step)
        raise HTTPException(401, "Google sign-in expired or could not be verified. Please try again.") from exc
    request.state.google_auth_step = "verified_identity_claims"
    email_claim = info.get("email")
    subject = info.get("sub")
    if (
        not isinstance(email_claim, str)
        or not email_claim.strip()
        or len(email_claim) > 320
        or not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or info.get("email_verified") is not True
    ):
        raise HTTPException(403, "A verified Google email is required")
    email = email_claim.strip().lower()
    identity = db.get(GoogleIdentity, subject)
    user = db.get(User, identity.user_id) if identity else db.query(User).filter(User.email == email).with_for_update().first()
    if identity and not user:
        raise HTTPException(403, "The linked account is unavailable")
    if user:
        request.state.google_auth_step = "existing_account"
        if not user.is_active:
            raise HTTPException(403, "Account is inactive")
        # Google proves the account identity. Route an existing user by the
        # server-stored role; a UI role selection never grants or changes it.
        if not identity:
            bound = db.query(GoogleIdentity).filter(GoogleIdentity.user_id == user.id).first()
            if bound:
                raise HTTPException(403, "Use the Google account already linked to this account")
            # Google is authoritative for Gmail and verified Workspace domains only.
            authoritative = email.endswith("@gmail.com") or bool(info.get("hd"))
            # Never turn an unverified pre-registered local account into an
            # automatically linked identity using only an email-string match.
            if not authoritative or not user.email_verified:
                request.state.google_auth_step = "existing_account_link"
                enforce_auth_limits(db, request, scope="login", identifier=email, limit=12, window_seconds=600, block_seconds=900)
                if not payload.password:
                    raise HTTPException(403, {"code": "GOOGLE_LINK_PASSWORD_REQUIRED", "message": "Enter your PlaceAI password once to link this Google account. If you did not create the existing account or do not know its password, use Forgot password first."})
                if not verify_password(payload.password, user.hashed_password):
                    raise HTTPException(401, "Incorrect password")
    else:
        request.state.google_auth_step = "new_account"
        if payload.role in {"institution_admin", "platform_admin"} or (payload.role == "recruiter" and not settings.public_recruiter_signup):
            raise HTTPException(403, "This role requires an existing account provisioned by an administrator")
        username_base = re.sub(r"[^A-Za-z0-9_]", "_", email.split("@")[0])[:55] or "student"
        username = f"{username_base}_{secrets.token_hex(6)}"
        user = User(email=email, username=username, hashed_password=get_hashed_password(secrets.token_urlsafe(40), check_breach=False),
                    role=UserRole(payload.role), email_verified=True)
        db.add(user)
        db.flush()
        if user.role == UserRole.student:
            db.add(StudentProfile(user_id=user.id, full_name=str(info.get("name", ""))[:200]))
        else:
            db.add(RecruiterProfile(user_id=user.id, full_name=str(info.get("name", ""))[:200], is_verified=False))
    request.state.google_auth_step = "identity_binding"
    if not identity:
        db.add(GoogleIdentity(subject=subject, user_id=user.id))
    # The signed cookie alone is replayable if restored. Consume the verified nonce
    # in durable state shared by Vercel/Render, before minting any PlaceAI session.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    claimed = db.execute(insert(RateLimitBucket).values(
        key_hash=hashlib.sha256(f"google-nonce|{nonce}".encode()).hexdigest(), scope="google-nonce",
        window_started_at=utcnow(), request_count=1, updated_at=utcnow()
    ).on_conflict_do_nothing(index_elements=["key_hash"]))
    if claimed.rowcount != 1:
        raise HTTPException(401, "Google sign-in was already used. Please sign in again.")
    user.email_verified = True
    user.last_login_at = utcnow()
    response.delete_cookie(COOKIE, path="/auth", secure=settings.is_production, httponly=True, samesite="strict")
    response.delete_cookie(COOKIE, path="/auth/google", secure=settings.is_production, httponly=True, samesite="strict")
    return user
