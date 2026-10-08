from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_student
from app.models import User
from app.roadmap_access import (
    CAREER_ROADMAP_FEATURE_CODE,
    CAREER_ROADMAP_ONE_TIME_PRICE_INR,
    roadmap_access_status,
)
from app.student_entitlements import (
    INDEPENDENT_MONTHLY_PLAN_CODE,
    INDEPENDENT_MONTHLY_PRICE_INR,
    TRIAL_DAYS,
    student_access_status,
)

router = APIRouter(prefix="/billing", tags=["Student Billing"])


@router.get("/status")
def billing_status(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = student_access_status(current_user, db)
    return {
        **status,
        "career_roadmap": roadmap_access_status(current_user, db, base_access=status),
    }


@router.get("/plans")
def billing_plans(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = student_access_status(current_user, db)
    roadmap = roadmap_access_status(current_user, db, base_access=status)
    independent = status["student_kind"] != "university"
    return {
        "student_kind": status["student_kind"],
        "plans": [] if not independent else [
            {
                "code": INDEPENDENT_MONTHLY_PLAN_CODE,
                "name": "PlaceAI Independent Student",
                "price_inr": INDEPENDENT_MONTHLY_PRICE_INR,
                "billing_period": "month",
                "trial_days": TRIAL_DAYS,
                "includes": [
                    "Placement readiness",
                    "Mock Interview Coach",
                    "Resume & AI readiness",
                    "Document vault",
                    "AI placement assistant",
                    "AI Career Roadmap after paid-plan activation",
                ],
            }
        ],
        "feature_unlocks": [] if not independent else [
            {
                "code": CAREER_ROADMAP_FEATURE_CODE,
                "name": "AI Career Roadmap",
                "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
                "billing_period": "one_time",
                "included_in_free_trial": False,
                "already_unlocked": roadmap["allowed"],
                "access_source": roadmap["access_source"],
            }
        ],
        "payment_provider": "pending_selection",
        "checkout_enabled": False,
        "roadmap_checkout_enabled": False,
    }


@router.post("/checkout")
def create_checkout(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = student_access_status(current_user, db)
    if status["student_kind"] == "university":
        raise HTTPException(status_code=409, detail="University-linked students are institution-sponsored and do not need a PlaceAI student subscription.")
    raise HTTPException(
        status_code=503,
        detail={
            "code": "PAYMENT_PROVIDER_NOT_ACTIVATED",
            "message": "The entitlement and subscription layer is ready. Live checkout will be enabled after the payment provider and merchant account are selected.",
            "recommended_plan": INDEPENDENT_MONTHLY_PLAN_CODE,
            "price_inr": INDEPENDENT_MONTHLY_PRICE_INR,
        },
    )


@router.post("/roadmap-checkout")
def create_roadmap_checkout(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = roadmap_access_status(current_user, db)
    if status["allowed"]:
        return {
            "already_unlocked": True,
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "access_source": status["access_source"],
        }
    raise HTTPException(
        status_code=503,
        detail={
            "code": "PAYMENT_PROVIDER_NOT_ACTIVATED",
            "message": "Career Roadmap is priced at ₹20 one-time, but secure live checkout is not active until the PlaceAI merchant/payment provider is configured.",
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "price_inr": CAREER_ROADMAP_ONE_TIME_PRICE_INR,
        },
    )
