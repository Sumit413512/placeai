from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.email_delivery import send_transactional_email
from app.models import AccountProtection, Organization, RecruiterProfile, RefreshSession, StudentProfile, User, UserRole
from app.telemetry_models import EmailDeliveryEvent
from app.rate_limit import enforce_auth_limits, enforce_rate_limit
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
_DUMMY_PASSWORD_HASH = get_hashed_password("Synthetic timing equalizer - not an account credential", check_breach=False)


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


def _token_response(user: User, response: Response, db: Session, *, revoke_jti: str | None = None,
                    mfa_verified: bool = False) -> TokenSchema:
    if not mfa_verified and not revoke_jti:
        from app.auth_protection import login_challenge
        challenge = login_challenge(user, db)
        if challenge:
            # No access/refresh credential or cookie until both factors succeed.
            return TokenSchema(**challenge)
    if revoke_jti:
        existing = db.query(RefreshSession).filter(RefreshSession.jti == revoke_jti, RefreshSession.revoked_at.is_(None)).first()
        if existing:
            existing.revoked_at = _utcnow()
    auth_version = int(user.auth_version or 1)
    if not revoke_jti:
        user.last_login_at = _utcnow()
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
    if not user:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    protection = db.get(AccountProtection, user.id)
    if protection and protection.verification_required and not user.email_verified:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return user


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(data: UserAuth, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="signup", identifier=str(data.email), limit=8, window_seconds=3600, block_seconds=3600)
    if data.role in ("institution_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Administrator accounts are provisioned by an authorized administrator")
    if data.role == "recruiter" and not settings.public_recruiter_signup:
        raise HTTPException(status_code=403, detail="Recruiter self-registration is disabled. Request an invite from an institution or platform administrator.")
    org = _resolve_org(data.organization_slug, db)
    email = data.email.lower()
    production_hash = get_hashed_password(data.password) if settings.is_production else None
    def pending_response():
        from app.auth_protection import deliver_verification
        background_tasks.add_task(deliver_verification, sessionmaker(bind=db.get_bind()), email)
        return JSONResponse(status_code=202, content={"verification_required": True,
            "message": "If registration can be completed, a verification link will be sent. Check your inbox, or use account recovery if you already have an account."})
    if db.query(User).filter(User.email == email).first():
        if settings.is_production:
            return pending_response()
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    if db.query(User).filter(User.username == data.username).first():
        if settings.is_production:
            return pending_response()
        raise HTTPException(status_code=400, detail="This username is already taken")

    user = User(
        email=email,
        username=data.username,
        hashed_password=production_hash or get_hashed_password(data.password),
        role=UserRole(data.role.value),
        organization_id=org.id if org else None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if settings.is_production:
            return pending_response()
        raise HTTPException(400, "Registration could not be completed") from None
    db.add(AccountProtection(user_id=user.id, verification_required=settings.is_production))

    if user.role == UserRole.student:
        db.add(StudentProfile(user_id=user.id, organization_id=org.id if org else None, college=org.name if org else None))
    elif user.role == UserRole.recruiter:
        db.add(RecruiterProfile(user_id=user.id, is_verified=False))

    db.commit()
    db.refresh(user)
    if settings.is_production:
        return pending_response()
    return user


@router.post("/login", response_model=TokenSchema)
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if len(form_data.username) > 320 or len(form_data.password) > 128:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    enforce_auth_limits(db, request, scope="login", identifier=form_data.username, limit=12, window_seconds=600, block_seconds=900)
    user = _authenticate(form_data.username, form_data.password, db)
    return _token_response(user, response, db)


@router.post("/login-json", response_model=TokenSchema)
def login_json(body: LoginJSON, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="login", identifier=str(body.email), limit=12, window_seconds=600, block_seconds=900)
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
    # Sign out all sessions so a copied in-memory access token cannot survive logout.
    # Accept the existing API bearer flow as well as the HttpOnly browser cookie.
    user = None
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = decode_refresh_payload(token)
            session = db.query(RefreshSession).filter(RefreshSession.jti == str(payload["jti"]), RefreshSession.revoked_at.is_(None)).first()
            if session:
                user = db.query(User).filter(User.id == session.user_id).with_for_update().first()
        except HTTPException:
            pass
    authorization = request.headers.get("authorization", "")
    if user is None and authorization.lower().startswith("bearer "):
        from app.utils import decode_token
        try:
            payload = decode_token(authorization.split(" ", 1)[1], settings.jwt_secret_key, "access")
            user = db.query(User).filter(User.email == payload["sub"], User.auth_version == payload["ver"]).with_for_update().first()
        except (ValueError, KeyError):
            pass
    if user:
        from app.auth_protection import revoke_sessions
        revoke_sessions(db, user)
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/auth", secure=settings.is_production, httponly=True, samesite="lax")


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/google-config")
def google_config(response: Response):
    from app.google_login import challenge
    return challenge(response)


@router.post("/google", response_model=TokenSchema)
def google_auth(payload: GoogleAuthRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    from app.google_login import authenticate
    try:
        user = authenticate(payload, request, response, db)
        return _token_response(user, response, db)
    except IntegrityError as exc:
        # A concurrent first sign-in can win either unique account binding. Never
        # switch identities or issue a session from the losing transaction.
        db.rollback()
        raise HTTPException(409, "Google account linking changed. Please sign in again.") from exc


def _send_reset_email(recipient: str, link: str) -> tuple[str, str | None]:
    """Send reset mail through the configured SMTP or Brevo transactional API transport."""
    return send_transactional_email(
        settings,
        recipient=recipient,
        subject=f"Reset your {settings.app_name} password",
        body=(
            "Use this one-time link to reset your password. It expires in 15 minutes:\n\n"
            f"{link}\n\n"
            "If you did not request this, ignore this email."
        ),
    )


def _record_reset_delivery_event(db: Session, outcome: str, reason_code: str | None) -> None:
    """Persist aggregate-safe telemetry without changing the public recovery response."""
    try:
        db.add(EmailDeliveryEvent(purpose="password_reset", outcome=outcome, reason_code=reason_code))
        db.commit()
    except Exception:
        db.rollback()


def _deliver_reset_after_response(sessions, user_id: str, email: str, link: str, token_hash: str,
                                  previous_hash: str | None, previous_expires: datetime | None) -> None:
    # Mail-provider latency must not reveal account existence in the HTTP response.
    delivery_outcome, delivery_reason = _send_reset_email(email, link)
    with sessions() as db:
        if delivery_outcome != "sent":
            db.query(User).filter(User.id == user_id, User.reset_token_hash == token_hash).update(
                {User.reset_token_hash: previous_hash, User.reset_token_expires: previous_expires},
                synchronize_session=False)
            db.commit()
        _record_reset_delivery_event(db, delivery_outcome, delivery_reason)


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db)):
    enforce_auth_limits(db, request, scope="forgot-password", identifier=str(body.email), limit=6, window_seconds=900, block_seconds=1800)
    generic = {"message": "If an account exists for that email, a password reset link has been sent."}
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active:
        return generic

    previous_hash = user.reset_token_hash
    previous_expires = user.reset_token_expires
    token = generate_reset_token()
    token_hash = hash_reset_token(token)
    user.reset_token_hash = token_hash
    user.reset_token_expires = _utcnow() + timedelta(minutes=15)
    db.commit()
    link = f"{settings.base_url}/?reset_token={token}"
    background_tasks.add_task(_deliver_reset_after_response, sessionmaker(bind=db.get_bind()),
                              user.id, user.email, link, token_hash, previous_hash, previous_expires)

    if settings.environment == "development" and settings.dev_show_reset_token:
        generic["development_reset_token"] = token
        generic["development_reset_link"] = link
    return generic


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="reset-password", limit=10, window_seconds=900, block_seconds=1800)
    digest = hash_reset_token(body.token)
    # Lock the recovery credential so a one-time token cannot be consumed by two
    # concurrent reset requests before either transaction clears it.
    user = (
        db.query(User)
        .filter(User.reset_token_hash == digest)
        .with_for_update()
        .first()
    )
    if not user or not user.reset_token_expires or user.reset_token_expires < _utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = get_hashed_password(body.new_password)
    user.must_change_password = False
    # The one-time link proves control of the registered mailbox; MFA remains enabled.
    user.email_verified = True
    protection = db.get(AccountProtection, user.id)
    if protection:
        protection.verification_required = False
        protection.challenge_hash = None
        protection.challenge_expires = None
        protection.email_token_hash = None
        protection.email_token_expires = None
    user.reset_token_hash = None
    user.reset_token_expires = None
    user.auth_version = int(user.auth_version or 1) + 1
    db.query(RefreshSession).filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).update(
        {RefreshSession.revoked_at: _utcnow()}, synchronize_session=False
    )
    db.commit()
    return {"message": "Password reset successfully"}
