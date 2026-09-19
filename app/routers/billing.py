from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_student
from app.models import User
from app.student_entitlements import (
    INDEPENDENT_MONTHLY_PLAN_CODE,
    INDEPENDENT_MONTHLY_PRICE_INR,
    TRIAL_DAYS,
    student_access_status,
)

router = APIRouter(prefix="/billing", tags=["Student Billing"])


@router.get("/status")
def billing_status(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    return student_access_status(current_user, db)


@router.get("/plans")
def billing_plans(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = student_access_status(current_user, db)
    return {
        "student_kind": status["student_kind"],
        "plans": [] if status["student_kind"] == "university" else [
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
                ],
            }
        ],
        "payment_provider": "pending_selection",
        "checkout_enabled": False,
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
