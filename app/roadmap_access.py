from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import StudentProfile, User, UserRole
from app.roadmap_models import StudentFeaturePurchase
from app.student_entitlements import student_access_status

CAREER_ROADMAP_FEATURE_CODE = "career_roadmap"
CAREER_ROADMAP_ONE_TIME_PRICE_INR = 20
CAREER_ROADMAP_ONE_TIME_PRICE_PAISE = CAREER_ROADMAP_ONE_TIME_PRICE_INR * 100


def roadmap_access_status(
    user: User,
    db: Session,
    *,
    base_access: dict | None = None,
) -> dict:
    if user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student access only")

    access = base_access or student_access_status(user, db)
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    access_mode = access.get("access_mode")
    if access_mode == "campus_sponsored":
        return {
            "allowed": True,
            "access_source": "institution",
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
            "payment_required": False,
            "checkout_enabled": False,
            "message": "Career Roadmap is included with your institution-sponsored PlaceAI access.",
        }

    if access_mode == "premium":
        return {
            "allowed": True,
            "access_source": "premium",
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
            "payment_required": False,
            "checkout_enabled": False,
            "message": "Career Roadmap is included with your active PlaceAI Premium plan.",
        }

    purchase = (
        db.query(StudentFeaturePurchase)
        .filter(
            StudentFeaturePurchase.student_id == profile.id,
            StudentFeaturePurchase.feature_code == CAREER_ROADMAP_FEATURE_CODE,
            StudentFeaturePurchase.status == "paid",
        )
        .order_by(StudentFeaturePurchase.purchased_at.desc(), StudentFeaturePurchase.created_at.desc())
        .first()
    )
    if purchase:
        return {
            "allowed": True,
            "access_source": "one_time_purchase",
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
            "payment_required": False,
            "checkout_enabled": False,
            "purchase_id": purchase.id,
            "message": "Career Roadmap is unlocked on this student account.",
        }

    if access_mode == "trial":
        message = (
            "Career Roadmap is not included in the 3-day free trial. "
            "Unlock this feature once for ₹20 or upgrade to PlaceAI Premium."
        )
    else:
        message = (
            "Unlock Career Roadmap once for ₹20 or activate PlaceAI Premium. "
            "University-sponsored students receive this feature through their institution."
        )
    return {
        "allowed": False,
        "access_source": "locked",
        "feature_code": CAREER_ROADMAP_FEATURE_CODE,
        "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
        "payment_required": True,
        "checkout_enabled": False,
        "message": message,
    }


def ensure_roadmap_access(user: User, db: Session) -> dict:
    access = roadmap_access_status(user, db)
    if access["allowed"]:
        return access
    raise HTTPException(
        status_code=402,
        detail={
            "code": "CAREER_ROADMAP_ACCESS_REQUIRED",
            "message": access["message"],
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
            "checkout_enabled": access["checkout_enabled"],
        },
    )


def require_roadmap_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    ensure_roadmap_access(current_user, db)
    return current_user
