from __future__ import annotations

import os
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.access_models import AccessRequest
from app.config import get_settings
from app.database import get_db
from app.dependencies import require_platform_admin
from app.models import User
from app.telemetry_models import EmailDeliveryEvent
from app.rate_limit import enforce_rate_limit
from app.routers.auth import _token_response, _utcnow
from app.schemas import TokenSchema
from app.utils import verify_password

settings = get_settings()
router = APIRouter(tags=["Access"])

ROLE_LABELS = {
    "student": "Student",
    "recruiter": "Recruiter",
    "institution_admin": "Institution Admin",
    "platform_admin": "Platform Admin",
}
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
        return value.strip()


class AccessRequestReview(BaseModel):
    status: Literal["new", "under_review", "approved", "rejected", "provisioned"]
    review_note: str | None = Field(default=None, max_length=3000)


def _public_access_response() -> dict[str, str]:
    """Return one invariant response so public callers cannot enumerate request state."""
    return {"message": PUBLIC_ACCESS_MESSAGE}


def _notify_access_request(item: AccessRequest) -> None:
    """Send a real transactional notification through configured SMTP/Brevo SMTP."""
    recipient = os.getenv("ACCESS_REQUEST_NOTIFY_TO", "").strip()
    if not (settings.smtp_host and settings.smtp_from and recipient):
        return
    message = EmailMessage()
    message["Subject"] = f"PlaceAI access request — {ROLE_LABELS.get(item.requested_role, item.requested_role)}"
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(
        "A new PlaceAI access request was submitted.\n\n"
        f"Role: {ROLE_LABELS.get(item.requested_role, item.requested_role)}\n"
        f"Name: {item.full_name}\n"
        f"Email: {item.work_email}\n"
        f"Organization: {item.organization_name or 'Not provided'}\n"
        f"Phone: {item.phone or 'Not provided'}\n"
        f"Message: {item.message or 'Not provided'}\n"
        f"Request ID: {item.id}\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        # Database persistence is the source of truth; mail delivery is retriable infrastructure.
        return


@router.post("/auth/login-role", response_model=TokenSchema)
def login_for_selected_role(
    body: RoleLoginRequest,
    request: Request,
    response: Response,
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
    db.commit()
    db.refresh(user)
    return _token_response(user, response, db)


@router.post("/public/access-requests", status_code=status.HTTP_202_ACCEPTED)
def create_access_request(
    body: AccessRequestCreate,
    request: Request,
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
            AccessRequest.status.in_(["new", "under_review", "approved"]),
        )
        .order_by(AccessRequest.created_at.desc())
        .first()
    )
    if existing:
        return _public_access_response()

    item = AccessRequest(
        requested_role=body.requested_role,
        full_name=body.full_name.strip(),
        work_email=email,
        organization_name=organization_name,
        phone=(body.phone or "").strip() or None,
        message=(body.message or "").strip() or None,
        status="new",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _notify_access_request(item)
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


@router.patch("/platform/access-requests/{request_id}")
def review_access_request(
    request_id: str,
    body: AccessRequestReview,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    item = db.query(AccessRequest).filter(AccessRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Access request not found")
    item.status = body.status
    item.review_note = (body.review_note or "").strip() or None
    item.reviewed_by_user_id = current_user.id
    item.updated_at = _utcnow()
    db.commit()
    db.refresh(item)
    return {
        "id": item.id,
        "status": item.status,
        "review_note": item.review_note,
        "reviewed_by_user_id": item.reviewed_by_user_id,
        "updated_at": item.updated_at,
    }


@router.get("/platform/integrations/status")
def integration_status(current_user: User = Depends(require_platform_admin)):
    """Return booleans only; never expose secret values."""
    return {
        "database": not settings.database_url.startswith("sqlite"),
        "brevo_smtp": bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from),
        "access_request_notifications": bool(os.getenv("ACCESS_REQUEST_NOTIFY_TO", "").strip()),
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

    credentials_consistent = bool(settings.smtp_user) == bool(settings.smtp_password)
    transport_configured = bool(settings.smtp_host and settings.smtp_from and credentials_consistent)
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
        "smtp_transport_configured": transport_configured,
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
