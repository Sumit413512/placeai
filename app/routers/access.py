from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.access_models import AccessRequest
from app.access_request_guards import ACTIVE_ACCESS_STATUSES, ensure_manual_access_status, normalize_access_request_name
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.dependencies import require_platform_admin
from app.email_delivery import (
    brevo_api_configured,
    send_transactional_email,
    smtp_transport_configured,
    transactional_email_configured,
)
from app.models import AuditEvent, User, UserRole
from app.rate_limit import enforce_rate_limit
from app.routers.auth import _token_response, _utcnow
from app.schemas import TokenSchema
from app.services import create_notification, record_audit
from app.telemetry_models import EmailDeliveryEvent
from app.utils import verify_password

settings = get_settings()
router = APIRouter(tags=["Access"])
logger = logging.getLogger("placeai.access")

ROLE_LABELS = {
    "student": "Student",
    "recruiter": "Recruiter",
    "institution_admin": "Institution Admin",
    "platform_admin": "Platform Admin",
}
CONTROLLED_LOGIN_ROLES = {UserRole.recruiter, UserRole.institution_admin, UserRole.platform_admin}
ACCESS_STATUSES = {"new", "under_review", "approved", "rejected", "provisioned"}
PUBLIC_ACCESS_MESSAGE = "Access request received. If eligible, an authorized administrator will review it."


class RoleLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    role: Literal["student", "recruiter", "institution_admin", "platform_admin"]


class AccessRequestCreate(BaseModel):
    requested_role: Literal["recruiter", "institution_admin", "platform_admin"]
    full_name: str = Field(min_length=2, max_length=200)
    work_email: EmailStr
    organization_name: str | None = Field(default=None, max_length=250)
    phone: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=3000)
    website: str | None = Field(default=None, max_length=300)

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return normalize_access_request_name(value)


class AccessRequestReview(BaseModel):
    status: Literal["new", "under_review", "approved", "rejected", "provisioned"]
    review_note: str | None = Field(default=None, max_length=3000)


def _public_access_response() -> dict[str, str]:
    """Return one invariant response so public callers cannot enumerate request state."""
    return {"message": PUBLIC_ACCESS_MESSAGE}


def _record_delivery_event(purpose: str, outcome: str, reason_code: str | None = None) -> None:
    """Persist PII-free delivery telemetry in an isolated transaction."""
    db = SessionLocal()
    try:
        db.add(EmailDeliveryEvent(purpose=purpose, outcome=outcome, reason_code=reason_code))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record access-email delivery telemetry")
    finally:
        db.close()


def _send_transactional_email(*, recipient: str, subject: str, body: str, purpose: str) -> bool:
    """Send one PlaceAI transactional email through the shared resilient transport."""
    outcome, reason = send_transactional_email(
        settings,
        recipient=recipient,
        subject=subject,
        body=body,
    )
    _record_delivery_event(purpose, outcome, reason)
    return outcome == "sent"


def _platform_admin_recipients(db: Session) -> list[str]:
    """Return active Platform Admin mailboxes plus the optional operational fallback."""
    recipients = {
        str(email).strip().lower()
        for (email,) in (
            db.query(User.email)
            .filter(User.role == UserRole.platform_admin, User.is_active.is_(True))
            .all()
        )
        if email and str(email).strip()
    }
    fallback = os.getenv("ACCESS_REQUEST_NOTIFY_TO", "").strip().lower()
    if fallback:
        recipients.add(fallback)
    return sorted(recipients)


def _access_request_payload(item: AccessRequest) -> dict[str, str | None]:
    return {
        "id": item.id,
        "requested_role": item.requested_role,
        "full_name": item.full_name,
        "work_email": item.work_email,
        "organization_name": item.organization_name,
        "phone": item.phone,
        "message": item.message,
        "status": item.status,
    }


def _deliver_new_access_request(payload: dict[str, str | None], admin_recipients: list[str]) -> None:
    role = ROLE_LABELS.get(str(payload["requested_role"]), str(payload["requested_role"]))
    admin_body = (
        "A new PlaceAI privileged-access request was submitted.\n\n"
        f"Role: {role}\n"
        f"Name: {payload['full_name']}\n"
        f"Email: {payload['work_email']}\n"
        f"Organization: {payload['organization_name'] or 'Not provided'}\n"
        f"Phone: {payload['phone'] or 'Not provided'}\n"
        f"Message: {payload['message'] or 'Not provided'}\n"
        f"Request ID: {payload['id']}\n\n"
        f"Review this request from the Platform Admin workspace: {settings.base_url}/\n"
    )
    for recipient in admin_recipients:
        _send_transactional_email(
            recipient=recipient,
            subject=f"PlaceAI access request — {role}",
            body=admin_body,
            purpose="access_request_admin",
        )

    requester = str(payload["work_email"] or "")
    _send_transactional_email(
        recipient=requester,
        subject="PlaceAI access request received",
        body=(
            f"Hello {payload['full_name']},\n\n"
            f"Your request for {role} access has been received. An authorized PlaceAI administrator "
            "will review it before any privileged account is provisioned.\n\n"
            f"Request ID: {payload['id']}\n\n"
            "You will receive another email when the review status changes. PlaceAI will never send "
            "a permanent password by email.\n"
        ),
        purpose="access_request_requester",
    )


def _deliver_access_status(payload: dict[str, str | None]) -> None:
    role = ROLE_LABELS.get(str(payload["requested_role"]), str(payload["requested_role"]))
    status_value = str(payload["status"] or "under_review")
    status_copy = {
        "new": "received",
        "under_review": "under review",
        "approved": "approved for provisioning",
        "rejected": "not approved",
        "provisioned": "provisioned",
    }.get(status_value, status_value.replace("_", " "))

    if status_value == "approved":
        next_step = (
            "Approval authorizes the next provisioning step. Your account is not usable until an "
            "authorized administrator creates the role-specific account and credentials."
        )
    elif status_value == "provisioned":
        next_step = (
            "Your privileged PlaceAI account has been provisioned. Complete the one-time password setup "
            "from the secure setup email before signing in."
        )
    elif status_value == "rejected":
        next_step = "No privileged account will be created from this request unless it is reviewed again."
    else:
        next_step = "No action is required from you while the administrator completes the review."

    _send_transactional_email(
        recipient=str(payload["work_email"] or ""),
        subject=f"PlaceAI access request update — {status_copy}",
        body=(
            f"Hello {payload['full_name']},\n\n"
            f"Your {role} access request is now {status_copy}.\n\n"
            f"{next_step}\n\n"
            f"Request ID: {payload['id']}\n"
        ),
        purpose="access_request_status",
    )


def _record_login_activity(db: Session, user: User) -> None:
    """Audit every successful role login and surface controlled-role logins to Platform Admins."""
    role_value = user.role.value
    record_audit(
        db,
        user,
        "auth.login.success",
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        metadata={"role": role_value, "provider": "password"},
    )
    if user.role not in CONTROLLED_LOGIN_ROLES:
        return
    role_label = ROLE_LABELS.get(role_value, role_value)
    admins = db.query(User).filter(User.role == UserRole.platform_admin, User.is_active.is_(True)).all()
    for admin in admins:
        create_notification(
            db,
            admin.id,
            f"{role_label} sign-in",
            f"{role_label} account {user.email} signed in to PlaceAI.",
            category="security",
            priority="high",
            link="notifications",
        )


def _deliver_controlled_login(payload: dict[str, str], admin_recipients: list[str]) -> None:
    role = payload["role"]
    for recipient in admin_recipients:
        _send_transactional_email(
            recipient=recipient,
            subject=f"PlaceAI security alert — {role} sign-in",
            body=(
                "A controlled PlaceAI account signed in successfully.\n\n"
                f"Role: {role}\n"
                f"Account: {payload['email']}\n"
                f"Time (UTC): {payload['signed_in_at']}\n\n"
                "If this sign-in is expected, no action is required. If it is unexpected, review the account and revoke access immediately.\n"
            ),
            purpose="controlled_login_alert",
        )


@router.post("/auth/login-role", response_model=TokenSchema)
def login_for_selected_role(
    body: RoleLoginRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Authenticate only when the selected workspace matches the account's actual role."""
    email = str(body.email).lower()
    enforce_rate_limit(
        db,
        request,
        scope="login",
        identifier=email,
        limit=12,
        window_seconds=600,
        block_seconds=900,
    )
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    if user.role.value != body.role:
        raise HTTPException(
            status_code=403,
            detail=f"This account does not have {ROLE_LABELS[body.role]} workspace access.",
        )

    user.last_login_at = _utcnow()
    _record_login_activity(db, user)
    db.commit()
    db.refresh(user)

    if user.role in CONTROLLED_LOGIN_ROLES:
        role_label = ROLE_LABELS.get(user.role.value, user.role.value)
        recipients = _platform_admin_recipients(db)
        background_tasks.add_task(
            _deliver_controlled_login,
            {
                "role": role_label,
                "email": user.email,
                "signed_in_at": user.last_login_at.isoformat(timespec="seconds") + "Z",
            },
            recipients,
        )
    return _token_response(user, response, db)


@router.post("/public/access-requests", status_code=status.HTTP_202_ACCEPTED)
def create_access_request(
    body: AccessRequestCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Capture privileged provisioning requests without exposing whether one already exists."""
    email = str(body.work_email).lower()
    enforce_rate_limit(
        db,
        request,
        scope="access-request",
        identifier=email,
        limit=5,
        window_seconds=3600,
        block_seconds=3600,
    )

    # Honeypot submissions deliberately receive the exact same response as genuine
    # new and duplicate requests. Nothing about request existence/review state is public.
    if body.website:
        return _public_access_response()

    organization_name = (body.organization_name or "").strip() or None
    if body.requested_role in {"recruiter", "institution_admin"} and not organization_name:
        raise HTTPException(status_code=422, detail="Organization name is required for this access type")

    existing = (
        db.query(AccessRequest)
        .filter(
            AccessRequest.work_email == email,
            AccessRequest.requested_role == body.requested_role,
            AccessRequest.status.in_(ACTIVE_ACCESS_STATUSES),
        )
        .order_by(AccessRequest.created_at.desc())
        .first()
    )
    if existing:
        return _public_access_response()

    item = AccessRequest(
        requested_role=body.requested_role,
        full_name=body.full_name,
        work_email=email,
        organization_name=organization_name,
        phone=(body.phone or "").strip() or None,
        message=(body.message or "").strip() or None,
        status="new",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    payload = _access_request_payload(item)
    recipients = _platform_admin_recipients(db)
    background_tasks.add_task(_deliver_new_access_request, payload, recipients)
    return _public_access_response()


@router.get("/platform/access-requests")
def list_access_requests(
    request_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AccessRequest)
    if request_status:
        if request_status not in ACCESS_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid access request status")
        query = query.filter(AccessRequest.status == request_status)
    rows = query.order_by(AccessRequest.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "requested_role": row.requested_role,
            "full_name": row.full_name,
            "work_email": row.work_email,
            "organization_name": row.organization_name,
            "phone": row.phone,
            "message": row.message,
            "status": row.status,
            "review_note": row.review_note,
            "reviewed_by_user_id": row.reviewed_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.get("/platform/auth-activity")
def platform_auth_activity(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Return successful role-login activity without exposing credentials or tokens."""
    del current_user
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "auth.login.success")
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": event.id,
            "email": event.actor.email if event.actor else None,
            "username": event.actor.username if event.actor else None,
            "role": event.details.get("role") or (event.actor.role.value if event.actor else None),
            "organization_id": event.organization_id,
            "provider": event.details.get("provider", "password"),
            "signed_in_at": event.created_at,
        }
        for event in events
    ]


@router.patch("/platform/access-requests/{request_id}")
def review_access_request(
    request_id: str,
    body: AccessRequestReview,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    item = db.query(AccessRequest).filter(AccessRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Access request not found")

    next_status = ensure_manual_access_status(body.status)
    previous_status = item.status
    previous_note = item.review_note
    item.status = next_status
    item.review_note = (body.review_note or "").strip() or None
    item.reviewed_by_user_id = current_user.id
    item.updated_at = _utcnow()
    if item.status != previous_status or item.review_note != previous_note:
        record_audit(
            db,
            current_user,
            "platform.access_request.reviewed",
            entity_type="access_request",
            entity_id=item.id,
            metadata={"previous_status": previous_status, "status": item.status},
        )
    db.commit()
    db.refresh(item)

    if item.status != previous_status:
        background_tasks.add_task(_deliver_access_status, _access_request_payload(item))

    return {
        "id": item.id,
        "status": item.status,
        "review_note": item.review_note,
        "reviewed_by_user_id": item.reviewed_by_user_id,
        "updated_at": item.updated_at,
    }


@router.get("/platform/integrations/status")
def integration_status(
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Return booleans and aggregate counts only; never expose secret values."""
    del current_user
    active_platform_admins = (
        db.query(User)
        .filter(User.role == UserRole.platform_admin, User.is_active.is_(True))
        .count()
    )
    fallback_configured = bool(os.getenv("ACCESS_REQUEST_NOTIFY_TO", "").strip())
    smtp_ready = smtp_transport_configured(settings)
    brevo_api_ready = brevo_api_configured(settings)
    email_ready = transactional_email_configured(settings)
    return {
        "database": not settings.database_url.startswith("sqlite"),
        "brevo_smtp": smtp_ready,
        "brevo_api": brevo_api_ready,
        "transactional_email": email_ready,
        "access_request_notifications": email_ready and (active_platform_admins > 0 or fallback_configured),
        "controlled_login_notifications": email_ready and active_platform_admins > 0,
        "active_platform_admins": active_platform_admins,
        "gemini": bool(settings.gemini_api_key),
        "google_sign_in": bool(settings.google_client_id),
        "production": settings.is_production,
    }


@router.get("/platform/integrations/password-reset-email")
def password_reset_email_observability(
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Expose PII-free password-reset delivery health to Platform Admin only."""
    del current_user
    now = _utcnow()
    cutoff = now - timedelta(hours=24)
    base = db.query(EmailDeliveryEvent).filter(EmailDeliveryEvent.purpose == "password_reset")
    recent = base.filter(EmailDeliveryEvent.created_at >= cutoff)
    last_attempt = base.order_by(EmailDeliveryEvent.created_at.desc()).first()
    last_success = base.filter(EmailDeliveryEvent.outcome == "sent").order_by(EmailDeliveryEvent.created_at.desc()).first()
    last_failure = base.filter(EmailDeliveryEvent.outcome == "failed").order_by(EmailDeliveryEvent.created_at.desc()).first()

    smtp_ready = smtp_transport_configured(settings)
    brevo_api_ready = brevo_api_configured(settings)
    transport_configured = transactional_email_configured(settings)
    authentication_enabled = bool(settings.smtp_user)
    authentication_configured = bool(settings.smtp_user and settings.smtp_password)

    if not transport_configured:
        operational_status = "not_configured"
    elif last_attempt and last_attempt.outcome == "failed":
        operational_status = "degraded"
    elif last_success:
        operational_status = "healthy"
    else:
        operational_status = "configured_no_recent_delivery"

    return {
        "status": operational_status,
        "transactional_email_configured": transport_configured,
        "smtp_transport_configured": smtp_ready,
        "brevo_api_configured": brevo_api_ready,
        "smtp_authentication_enabled": authentication_enabled,
        "smtp_authentication_configured": authentication_configured,
        "tls_enabled": settings.smtp_tls,
        "base_url_https": settings.base_url.startswith("https://"),
        "attempts_24h": recent.count(),
        "successes_24h": recent.filter(EmailDeliveryEvent.outcome == "sent").count(),
        "failures_24h": recent.filter(EmailDeliveryEvent.outcome == "failed").count(),
        "not_configured_24h": recent.filter(EmailDeliveryEvent.outcome == "not_configured").count(),
        "last_attempt_at": last_attempt.created_at if last_attempt else None,
        "last_success_at": last_success.created_at if last_success else None,
        "last_failure_at": last_failure.created_at if last_failure else None,
    }
