from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_student
from app.models import IndividualStudentAccess, Organization, StudentProfile, User, UserRole
from app.placement_access import utcnow_naive

settings = get_settings()

INDIVIDUAL_PLAN_CODE = "individual_pro_monthly"
INDIVIDUAL_PREMIUM_FEATURES = (
    "Readiness score",
    "Mock Interview Coach",
    "Resume & AI Readiness",
    "Document vault uploads",
    "AI placement assistant",
)


def _student_profile(user: User, db: Session) -> StudentProfile | None:
    if user.role != UserRole.student:
        return None
    return db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()


def university_organization_id(user: User, profile: StudentProfile | None = None) -> str | None:
    return (profile.organization_id if profile and profile.organization_id else None) or user.organization_id


def is_university_student(user: User, db: Session, profile: StudentProfile | None = None) -> bool:
    profile = profile or _student_profile(user, db)
    return bool(university_organization_id(user, profile))


def campus_verification_state(user: User, db: Session, profile: StudentProfile | None = None) -> tuple[bool, str | None]:
    profile = profile or _student_profile(user, db)
    org_id = university_organization_id(user, profile)
    if not profile or not org_id:
        return False, None
    organization = db.query(Organization).filter(Organization.id == org_id).first()
    active = bool(organization and organization.is_active)
    return bool(active and profile.is_verified), organization.name if organization else None


def get_or_create_individual_access(
    user: User,
    db: Session,
    *,
    commit: bool = True,
) -> IndividualStudentAccess | None:
    if user.role != UserRole.student:
        return None
    profile = _student_profile(user, db)
    if is_university_student(user, db, profile):
        return None

    row = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).first()
    if row:
        return row

    now = utcnow_naive()
    row = IndividualStudentAccess(
        user_id=user.id,
        status="trialing",
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=settings.student_individual_trial_days),
        plan_code=INDIVIDUAL_PLAN_CODE,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def refresh_individual_status(row: IndividualStudentAccess, db: Session, *, commit: bool = True) -> str:
    now = utcnow_naive()
    if row.paid_access_until and row.paid_access_until > now:
        normalized = "active"
    elif row.trial_ends_at > now:
        normalized = "trialing"
    elif row.status == "cancelled":
        normalized = "cancelled"
    else:
        normalized = "expired"

    if row.status != normalized:
        row.status = normalized
        if commit:
            db.commit()
            db.refresh(row)
    return normalized


def premium_student_access(user: User, db: Session) -> bool:
    if user.role != UserRole.student:
        return False
    if is_university_student(user, db):
        return True
    row = get_or_create_individual_access(user, db)
    if not row:
        return False
    return refresh_individual_status(row, db) in {"trialing", "active"}


def require_premium_student_access(user: User, db: Session) -> None:
    if user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student access only")
    if premium_student_access(user, db):
        return
    raise HTTPException(
        status_code=402,
        detail={
            "code": "INDIVIDUAL_PLAN_REQUIRED",
            "message": "Your 3-day PlaceAI preparation trial has ended. Upgrade Individual Pro to continue using premium preparation tools.",
            "billing_path": "/billing/student/status",
        },
    )


def student_access_payload(user: User, db: Session) -> dict:
    if user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student access only")

    profile = _student_profile(user, db)
    org_id = university_organization_id(user, profile)
    campus_verified, organization_name = campus_verification_state(user, db, profile)

    if org_id:
        return {
            "account_type": "university",
            "university_associated": True,
            "organization_id": org_id,
            "organization_name": organization_name,
            "campus_verified": campus_verified,
            "premium_access": True,
            "payment_required": False,
            "status": "university_full",
            "trial_started_at": None,
            "trial_ends_at": None,
            "paid_access_until": None,
            "plan": None,
            "message": (
                "University-associated student access is included. Campus-specific placement content remains protected by institution verification."
                if not campus_verified
                else "University-associated student access is active with verified campus placement access."
            ),
        }

    row = get_or_create_individual_access(user, db)
    status = refresh_individual_status(row, db) if row else "expired"
    now = utcnow_naive()
    seconds_remaining = max(0, int((row.trial_ends_at - now).total_seconds())) if row and status == "trialing" else 0
    premium = status in {"trialing", "active"}

    return {
        "account_type": "individual",
        "university_associated": False,
        "organization_id": None,
        "organization_name": None,
        "campus_verified": False,
        "premium_access": premium,
        "payment_required": not premium,
        "status": status,
        "trial_started_at": row.trial_started_at if row else None,
        "trial_ends_at": row.trial_ends_at if row else None,
        "trial_seconds_remaining": seconds_remaining,
        "paid_access_until": row.paid_access_until if row else None,
        "plan": {
            "code": INDIVIDUAL_PLAN_CODE,
            "name": "PlaceAI Individual Pro",
            "price_inr": settings.student_individual_monthly_price_inr,
            "billing_period": "month",
            "trial_days": settings.student_individual_trial_days,
            "premium_features": list(INDIVIDUAL_PREMIUM_FEATURES),
        },
        "message": (
            "Your individual 3-day preparation trial is active."
            if status == "trialing"
            else "Your Individual Pro access is active."
            if status == "active"
            else "Your individual preparation trial has ended. Upgrade to restore premium preparation tools."
        ),
    }


def premium_student_guard(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency for preparation features included by university or individual entitlement."""
    require_premium_student_access(current_user, db)
    return current_user
