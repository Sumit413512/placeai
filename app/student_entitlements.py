from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.billing_models import StudentSubscription
from app.database import get_db
from app.dependencies import get_current_user
from app.models import StudentProfile, User, UserRole
from app.placement_access import utcnow_naive

TRIAL_DAYS = 3
INDEPENDENT_MONTHLY_PRICE_INR = 299
INDEPENDENT_MONTHLY_PLAN_CODE = "placeai_independent_monthly"


def student_access_status(user: User, db: Session) -> dict:
    if user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student access only")

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    if profile.organization_id or user.organization_id:
        return {
            "student_kind": "university",
            "access_mode": "campus_sponsored",
            "premium_access": True,
            "campus_access": True,
            "trial_started_at": None,
            "trial_ends_at": None,
            "trial_days": TRIAL_DAYS,
            "trial_remaining_seconds": None,
            "plan_code": "campus_sponsored",
            "price_inr": 0,
            "payment_required": False,
        }

    now = utcnow_naive()
    subscription = (
        db.query(StudentSubscription)
        .filter(
            StudentSubscription.student_id == profile.id,
            StudentSubscription.status == "active",
            StudentSubscription.expires_at > now,
        )
        .order_by(StudentSubscription.expires_at.desc())
        .first()
    )
    if subscription:
        return {
            "student_kind": "independent",
            "access_mode": "premium",
            "premium_access": True,
            "campus_access": False,
            "trial_started_at": user.created_at,
            "trial_ends_at": user.created_at + timedelta(days=TRIAL_DAYS),
            "trial_days": TRIAL_DAYS,
            "trial_remaining_seconds": 0,
            "plan_code": subscription.plan_code,
            "price_inr": subscription.amount_paise // 100,
            "subscription_expires_at": subscription.expires_at,
            "payment_required": False,
        }

    trial_start = user.created_at
    trial_end = trial_start + timedelta(days=TRIAL_DAYS)
    remaining = max(0, int((trial_end - now).total_seconds()))
    in_trial = remaining > 0
    return {
        "student_kind": "independent",
        "access_mode": "trial" if in_trial else "expired",
        "premium_access": in_trial,
        "campus_access": False,
        "trial_started_at": trial_start,
        "trial_ends_at": trial_end,
        "trial_days": TRIAL_DAYS,
        "trial_remaining_seconds": remaining,
        "plan_code": INDEPENDENT_MONTHLY_PLAN_CODE,
        "price_inr": INDEPENDENT_MONTHLY_PRICE_INR,
        "payment_required": not in_trial,
    }


def ensure_student_premium_access(user: User, db: Session) -> dict:
    access = student_access_status(user, db)
    if not access["premium_access"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "PREMIUM_REQUIRED",
                "message": "Your 3-day PlaceAI independent-student trial has ended. Upgrade to continue using preparation features.",
                "price_inr": INDEPENDENT_MONTHLY_PRICE_INR,
                "plan_code": INDEPENDENT_MONTHLY_PLAN_CODE,
            },
        )
    return access


def require_student_premium_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    ensure_student_premium_access(current_user, db)
    return current_user
