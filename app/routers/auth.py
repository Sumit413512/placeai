from __future__ import annotations

import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Organization, RecruiterProfile, RefreshSession, StudentProfile, User, UserRole
from app.telemetry_models import EmailDeliveryEvent
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginJSON,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenSchema,
    UserAuth,
    UserOut,
)
from app.utils import (
    create_access_token,
    create_refresh_token,
    decode_refresh_payload,
    generate_reset_token,
    get_hashed_password,
    hash_reset_token,
    verify_password,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication"])
COOKIE_NAME = "placeai_refresh"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _resolve_org(slug: str | None, db: Session) -> Organization | None:
    if not slug:
        return None
    org = db.query(Organization).filter(Organization.slug == slug.lower(), Organization.is_active.is_(True)).first()
    if not org:
        raise HTTPException(status_code=400, detail="Institution code is invalid or inactive")
    return org


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/auth",
    )


def _register_refresh_session(user: User, token: str, db: Session) -> None:
    payload = decode_refresh_payload(token)
    session = RefreshSession(
        jti=str(payload["jti"]),
        user_id=user.id,
        auth_version=int(user.auth_version or 1),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc).replace(tzinfo=None),
    )
    db.add(session)


def _token_response(user: User, response: Response, db: Session, *, revoke_jti: str | None = None) -> TokenSchema:
    if revoke_jti:
        existing = db.query(RefreshSession).filter(RefreshSession.jti == revoke_jti, RefreshSession.revoked_at.is_(None)).first()
        if existing:
            existing.revoked_at = _utcnow()
    auth_version = int(user.auth_version or 1)
    access = create_access_token(user.email, auth_version)
    refresh = create_refresh_token(user.email, auth_version)
    _register_refresh_session(user, refresh, db)
    db.commit()
    _set_refresh_cookie(response, refresh)
    return TokenSchema(
        access_token=access,
        refresh_token=None if settings.is_production else refresh,
        expires_in=settings.access_token_minutes * 60,
    )


def _authenticate(email: str, password: str, db: Session) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    user.last_login_at = _utcnow()
    db.commit()
    db.refresh(user)
    return user


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(data: UserAuth, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="signup", identifier=str(data.email), limit=8, window_seconds=3600, block_seconds=3600)
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="This username is already taken")

    if data.role in ("institution_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Administrator accounts are provisioned by an authorized administrator")
    if data.role == "recruiter" and not settings.public_recruiter_signup:
        raise HTTPException(status_code=403, detail="Recruiter self-registration is disabled. Request an invite from an institution or platform administrator.")

    org = _resolve_org(data.organization_slug, db)
    user = User(
        email=email,
        username=data.username,
        hashed_password=get_hashed_password(data.password),
        role=UserRole(data.role.value),
        organization_id=org.id if org else None,
    )
    db.add(user)
    db.flush()

    if user.role == UserRole.student:
        db.add(StudentProfile(user_id=user.id, organization_id=org.id if org else None, college=org.name if org else None))
    elif user.role == UserRole.recruiter:
        db.add(RecruiterProfile(user_id=user.id, is_verified=False))

    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenSchema)
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if len(form_data.username) > 320 or len(form_data.password) > 128:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    enforce_rate_limit(db, request, scope="login", identifier=form_data.username, limit=12, window_seconds=600, block_seconds=900)
    user = _authenticate(form_data.username, form_data.password, db)
    return _token_response(user, response, db)


@router.post("/login-json", response_model=TokenSchema)
def login_json(body: LoginJSON, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="login", identifier=str(body.email), limit=12, window_seconds=600, block_seconds=900)
    user = _authenticate(body.email, body.password, db)
    return _token_response(user, response, db)


@router.post("/refresh", response_model=TokenSchema)
def refresh_token(
    body: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate a refresh token exactly once, including under concurrent requests.

    The refresh-session row is locked until `_token_response` revokes the current JTI,
    creates its successor and commits. A concurrent request using the same token blocks
    on this row; after the first rotation commits it observes `revoked_at` and is denied.
    """
    enforce_rate_limit(db, request, scope="refresh", limit=60, window_seconds=600, block_seconds=600)
    token = body.refresh_token or request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    payload = decode_refresh_payload(token)
    email = str(payload["sub"])
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or int(payload.get("ver", 0)) != int(user.auth_version or 1):
        raise HTTPException(status_code=401, detail="Account session is unavailable")

    session = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.jti == str(payload["jti"]),
            RefreshSession.user_id == user.id,
        )
        .with_for_update()
        .first()
    )
    if (
        not session
        or session.revoked_at is not None
        or session.expires_at <= _utcnow()
        or session.auth_version != int(user.auth_version or 1)
    ):
        raise HTTPException(status_code=401, detail="Refresh session is invalid or revoked")

    return _token_response(user, response, db, revoke_jti=session.jti)

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = decode_refresh_payload(token)
            session = db.query(RefreshSession).filter(RefreshSession.jti == str(payload["jti"]), RefreshSession.revoked_at.is_(None)).first()
            if session:
                session.revoked_at = _utcnow()
                db.commit()
        except HTTPException:
            pass
    response.delete_cookie(COOKIE_NAME, path="/auth")


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/google-config")
def google_config():
    return {"enabled": bool(settings.google_client_id), "client_id": settings.google_client_id if settings.google_client_id else None}


@router.post("/google", response_model=TokenSchema)
def google_auth(payload: GoogleAuthRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="google-auth", limit=30, window_seconds=600, block_seconds=900)
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured")
    credential = payload.credential
    requested_role = payload.role
    if requested_role == "recruiter" and not settings.public_recruiter_signup:
        raise HTTPException(
            status_code=403,
            detail="Recruiter self-registration is disabled. Request an invite from an institution or platform administrator.",
        )
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), settings.google_client_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Google authentication failed")

    email = str(info.get("email", "")).lower()
    if not email:
        raise HTTPException(status_code=400, detail="Google account did not provide an email address")
    if info.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Google account email must be verified")
    user = db.query(User).filter(User.email == email).first()
    if user:
        if user.role in {UserRole.institution_admin, UserRole.platform_admin}:
            raise HTTPException(
                status_code=403,
                detail="Google sign-in is not enabled for privileged administrator accounts",
            )
        if user.role.value != requested_role:
            raise HTTPException(status_code=403, detail="Google sign-in role does not match this account")
    if not user:
        username_base = email.split("@")[0].replace(".", "_").replace("-", "_")[:65]
        username = username_base
        i = 1
        while db.query(User).filter(User.username == username).first():
            i += 1
            username = f"{username_base}_{i}"
        role = UserRole.recruiter if requested_role == "recruiter" else UserRole.student
        user = User(
            email=email,
            username=username,
            hashed_password=get_hashed_password(generate_reset_token()),
            role=role,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        if role == UserRole.student:
            db.add(StudentProfile(user_id=user.id, full_name=info.get("name")))
        else:
            db.add(RecruiterProfile(user_id=user.id, full_name=info.get("name"), is_verified=False))
        db.commit()
        db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return _token_response(user, response, db)


def _send_reset_email(recipient: str, link: str) -> tuple[str, str | None]:
    """Send reset mail and return only sanitized operational outcome codes."""
    credentials_consistent = bool(settings.smtp_user) == bool(settings.smtp_password)
    if not (settings.smtp_host and settings.smtp_from and credentials_consistent):
        return "not_configured", "smtp_not_configured"
    message = EmailMessage()
    message["Subject"] = f"Reset your {settings.app_name} password"
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(f"Use this one-time link to reset your password. It expires in 15 minutes:\n\n{link}\n\nIf you did not request this, ignore this email.")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return "sent", None
    except Exception:
        # Never persist exception text: SMTP/provider errors can contain addresses or infrastructure detail.
        return "failed", "smtp_delivery_failed"


def _record_reset_delivery_event(db: Session, outcome: str, reason_code: str | None) -> None:
    """Persist aggregate-safe telemetry without changing the public recovery response."""
    try:
        db.add(EmailDeliveryEvent(purpose="password_reset", outcome=outcome, reason_code=reason_code))
        db.commit()
    except Exception:
        db.rollback()


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="forgot-password", identifier=str(body.email), limit=6, window_seconds=900, block_seconds=1800)
    generic = {"message": "If an account exists for that email, a password reset link has been sent."}
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active:
        return generic

    token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(token)
    user.reset_token_expires = _utcnow() + timedelta(minutes=15)
    db.commit()
    link = f"{settings.base_url}/?reset_token={token}"
    delivery_outcome, delivery_reason = _send_reset_email(user.email, link)
    _record_reset_delivery_event(db, delivery_outcome, delivery_reason)

    if settings.environment == "development" and settings.dev_show_reset_token:
        generic["development_reset_token"] = token
        generic["development_reset_link"] = link
    return generic


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="reset-password", limit=10, window_seconds=900, block_seconds=1800)
    digest = hash_reset_token(body.token)
    user = db.query(User).filter(User.reset_token_hash == digest).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < _utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = get_hashed_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    user.auth_version = int(user.auth_version or 1) + 1
    db.query(RefreshSession).filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).update(
        {RefreshSession.revoked_at: _utcnow()}, synchronize_session=False
    )
    db.commit()
    return {"message": "Password reset successfully"}
