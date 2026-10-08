from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.billing_models import StudentSubscription
from app.cashfree_payments import (
    CASHFREE_CURRENCY,
    CASHFREE_PROVIDER,
    CashfreeClient,
    CashfreePaymentError,
    amount_to_paise,
    successful_payment,
    verify_webhook_signature,
)
from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import require_student
from app.models import StudentProfile, User, utcnow
from app.roadmap_access import (
    CAREER_ROADMAP_FEATURE_CODE,
    CAREER_ROADMAP_ONE_TIME_PRICE_INR,
    CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
    roadmap_access_status,
)
from app.roadmap_models import StudentFeaturePurchase
from app.student_entitlements import (
    INDEPENDENT_MONTHLY_PLAN_CODE,
    INDEPENDENT_MONTHLY_PRICE_INR,
    TRIAL_DAYS,
    student_access_status,
)

router = APIRouter(prefix="/billing", tags=["Student Billing"])

INDEPENDENT_ACCESS_DAYS = 30
INDEPENDENT_MONTHLY_PRICE_PAISE = INDEPENDENT_MONTHLY_PRICE_INR * 100


def _payment_http_error(error: CashfreePaymentError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


def _checkout_unavailable(*, feature_code: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {
        "code": "PAYMENT_PROVIDER_NOT_ACTIVATED",
        "message": "Secure PlaceAI checkout is not active yet. Merchant/KYC activation and production payment credentials are required.",
        "payment_provider": CASHFREE_PROVIDER,
    }
    if feature_code:
        detail["feature_code"] = feature_code
    return HTTPException(status_code=503, detail=detail)


def _client(settings: Settings) -> CashfreeClient:
    if not settings.cashfree_checkout_ready:
        raise _checkout_unavailable()
    return CashfreeClient(
        app_id=settings.cashfree_app_id,
        secret_key=settings.cashfree_secret_key,
        environment=settings.cashfree_environment,
        api_version=settings.cashfree_api_version,
        timeout_seconds=settings.cashfree_timeout_seconds,
    )


def _profile(current_user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _cashfree_phone(profile: StudentProfile) -> str:
    digits = re.sub(r"\D", "", profile.phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[-10:]
    if len(digits) != 10:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PAYMENT_PHONE_REQUIRED",
                "message": "Add a valid 10-digit mobile number to your PlaceAI profile before opening secure checkout.",
            },
        )
    return digits


def _new_order_id(kind: str) -> str:
    prefix = "pai_rm" if kind == "roadmap" else "pai_sub"
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _checkout_response(*, provider_order: dict[str, Any], settings: Settings, product: str, amount_paise: int) -> dict[str, Any]:
    return {
        "provider": CASHFREE_PROVIDER,
        "checkout_enabled": True,
        "sdk_mode": "production" if settings.cashfree_environment == "production" else "sandbox",
        "order_id": provider_order["order_id"],
        "payment_session_id": provider_order["payment_session_id"],
        "product": product,
        "amount_inr": amount_paise // 100,
        "currency": CASHFREE_CURRENCY,
    }


def _pending_reference(db: Session, order_id: str) -> tuple[str, StudentFeaturePurchase | StudentSubscription] | None:
    purchase = db.query(StudentFeaturePurchase).filter(StudentFeaturePurchase.provider_order_id == order_id).first()
    if purchase:
        return "roadmap", purchase
    subscription = db.query(StudentSubscription).filter(StudentSubscription.provider_subscription_id == order_id).first()
    if subscription:
        return "subscription", subscription
    return None


def _validate_provider_order(*, order_id: str, order: dict[str, Any], expected_amount_paise: int, expected_user_id: str | None) -> None:
    if str(order.get("order_id") or "") != order_id:
        raise CashfreePaymentError("PAYMENT_ORDER_MISMATCH", "Payment provider returned a mismatched order.")
    if str(order.get("order_currency") or "").upper() != CASHFREE_CURRENCY:
        raise CashfreePaymentError("PAYMENT_CURRENCY_MISMATCH", "Payment currency did not match the PlaceAI order.")
    if amount_to_paise(order.get("order_amount")) != expected_amount_paise:
        raise CashfreePaymentError("PAYMENT_AMOUNT_MISMATCH", "Payment amount did not match the PlaceAI order.")
    if expected_user_id:
        customer = order.get("customer_details") if isinstance(order.get("customer_details"), dict) else {}
        if str(customer.get("customer_id") or "") != expected_user_id:
            raise CashfreePaymentError("PAYMENT_CUSTOMER_MISMATCH", "Payment customer did not match the signed-in PlaceAI account.")


def _validate_success_payment(payment: dict[str, Any], expected_amount_paise: int) -> str:
    if str(payment.get("payment_currency") or CASHFREE_CURRENCY).upper() != CASHFREE_CURRENCY:
        raise CashfreePaymentError("PAYMENT_CURRENCY_MISMATCH", "Payment currency did not match the PlaceAI order.")
    if amount_to_paise(payment.get("payment_amount")) != expected_amount_paise:
        raise CashfreePaymentError("PAYMENT_AMOUNT_MISMATCH", "Payment amount did not match the PlaceAI order.")
    payment_id = str(payment.get("cf_payment_id") or payment.get("payment_id") or "").strip()
    if not payment_id:
        raise CashfreePaymentError("PAYMENT_PROVIDER_RESPONSE_INVALID", "Successful payment did not include a provider payment reference.")
    return payment_id


def _activate_reference(
    *,
    db: Session,
    kind: str,
    reference: StudentFeaturePurchase | StudentSubscription,
    payment_id: str,
) -> dict[str, Any]:
    now = utcnow()
    if kind == "roadmap":
        purchase = reference
        assert isinstance(purchase, StudentFeaturePurchase)
        if purchase.status == "paid":
            return {
                "verified": True,
                "already_processed": True,
                "product": CAREER_ROADMAP_FEATURE_CODE,
                "access_source": "one_time_purchase",
            }
        purchase.status = "paid"
        purchase.provider_payment_id = payment_id
        purchase.purchased_at = now
        db.commit()
        return {
            "verified": True,
            "already_processed": False,
            "product": CAREER_ROADMAP_FEATURE_CODE,
            "access_source": "one_time_purchase",
        }

    subscription = reference
    assert isinstance(subscription, StudentSubscription)
    if subscription.status == "active" and subscription.provider_payment_id:
        return {
            "verified": True,
            "already_processed": True,
            "product": INDEPENDENT_MONTHLY_PLAN_CODE,
            "access_source": "premium",
            "expires_at": subscription.expires_at,
        }

    latest_active = (
        db.query(StudentSubscription)
        .filter(
            StudentSubscription.student_id == subscription.student_id,
            StudentSubscription.id != subscription.id,
            StudentSubscription.status == "active",
            StudentSubscription.expires_at > now,
        )
        .order_by(StudentSubscription.expires_at.desc())
        .first()
    )
    starts_at = latest_active.expires_at if latest_active and latest_active.expires_at > now else now
    subscription.status = "active"
    subscription.provider_payment_id = payment_id
    subscription.starts_at = starts_at
    subscription.expires_at = starts_at + timedelta(days=INDEPENDENT_ACCESS_DAYS)
    db.commit()
    return {
        "verified": True,
        "already_processed": False,
        "product": INDEPENDENT_MONTHLY_PLAN_CODE,
        "access_source": "premium",
        "expires_at": subscription.expires_at,
    }


def _verify_and_activate(
    *,
    db: Session,
    settings: Settings,
    order_id: str,
    expected_user: User | None,
) -> dict[str, Any]:
    found = _pending_reference(db, order_id)
    if not found:
        raise HTTPException(status_code=404, detail={"code": "PAYMENT_ORDER_NOT_FOUND", "message": "PlaceAI payment order was not found."})
    kind, reference = found

    profile = db.query(StudentProfile).filter(StudentProfile.id == reference.student_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail={"code": "PAYMENT_ACCOUNT_NOT_FOUND", "message": "Student account for this order was not found."})
    if expected_user and profile.user_id != expected_user.id:
        raise HTTPException(status_code=403, detail={"code": "PAYMENT_ORDER_FORBIDDEN", "message": "This payment order belongs to another PlaceAI account."})

    expected_amount = reference.amount_paise
    cashfree = _client(settings)
    try:
        order = cashfree.get_order(order_id)
        _validate_provider_order(
            order_id=order_id,
            order=order,
            expected_amount_paise=expected_amount,
            expected_user_id=profile.user_id,
        )
        payment = successful_payment(cashfree.get_order_payments(order_id))
        if not payment:
            return {"verified": False, "pending": True, "order_id": order_id, "product": kind}
        payment_id = _validate_success_payment(payment, expected_amount)
    except CashfreePaymentError as exc:
        raise _payment_http_error(exc) from exc

    result = _activate_reference(db=db, kind=kind, reference=reference, payment_id=payment_id)
    return {**result, "order_id": order_id}


@router.get("/status")
def billing_status(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    status = student_access_status(current_user, db)
    return {
        **status,
        "career_roadmap": roadmap_access_status(current_user, db, base_access=status),
    }


@router.get("/plans")
def billing_plans(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    status = student_access_status(current_user, db)
    roadmap = roadmap_access_status(current_user, db, base_access=status)
    independent = status["student_kind"] != "university"
    checkout_ready = bool(independent and settings.cashfree_checkout_ready)
    return {
        "student_kind": status["student_kind"],
        "plans": [] if not independent else [
            {
                "code": INDEPENDENT_MONTHLY_PLAN_CODE,
                "name": "PlaceAI Independent Student",
                "price_inr": INDEPENDENT_MONTHLY_PRICE_INR,
                "billing_period": "30_day_access",
                "trial_days": TRIAL_DAYS,
                "auto_renew": False,
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
        "payment_provider": CASHFREE_PROVIDER,
        "checkout_enabled": checkout_ready,
        "roadmap_checkout_enabled": bool(checkout_ready and not roadmap["allowed"]),
        "checkout_mode": settings.cashfree_environment if checkout_ready else None,
    }


@router.post("/checkout")
def create_checkout(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    status = student_access_status(current_user, db)
    if status["student_kind"] == "university":
        raise HTTPException(status_code=409, detail="University-linked students are institution-sponsored and do not need a PlaceAI student subscription.")
    if not settings.cashfree_checkout_ready:
        raise _checkout_unavailable()

    profile = _profile(current_user, db)
    phone = _cashfree_phone(profile)
    order_id = _new_order_id("subscription")
    try:
        provider_order = _client(settings).create_order(
            order_id=order_id,
            amount_paise=INDEPENDENT_MONTHLY_PRICE_PAISE,
            customer_id=current_user.id,
            customer_email=current_user.email,
            customer_phone=phone,
            return_url=f"{settings.base_url}/?placeai_payment=1&order_id={order_id}",
            notify_url=f"{settings.base_url}/billing/cashfree/webhook",
            order_note="PlaceAI Independent Student 30-day access",
        )
    except CashfreePaymentError as exc:
        raise _payment_http_error(exc) from exc

    now = utcnow()
    pending = StudentSubscription(
        student_id=profile.id,
        plan_code=INDEPENDENT_MONTHLY_PLAN_CODE,
        status="pending",
        provider=CASHFREE_PROVIDER,
        provider_subscription_id=order_id,
        amount_paise=INDEPENDENT_MONTHLY_PRICE_PAISE,
        starts_at=now,
        expires_at=now,
    )
    db.add(pending)
    db.commit()
    return _checkout_response(
        provider_order=provider_order,
        settings=settings,
        product=INDEPENDENT_MONTHLY_PLAN_CODE,
        amount_paise=INDEPENDENT_MONTHLY_PRICE_PAISE,
    )


@router.post("/roadmap-checkout")
def create_roadmap_checkout(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    access = roadmap_access_status(current_user, db)
    if access["allowed"]:
        return {
            "already_unlocked": True,
            "feature_code": CAREER_ROADMAP_FEATURE_CODE,
            "access_source": access["access_source"],
        }
    if not settings.cashfree_checkout_ready:
        raise _checkout_unavailable(feature_code=CAREER_ROADMAP_FEATURE_CODE)

    profile = _profile(current_user, db)
    phone = _cashfree_phone(profile)
    order_id = _new_order_id("roadmap")
    try:
        provider_order = _client(settings).create_order(
            order_id=order_id,
            amount_paise=CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
            customer_id=current_user.id,
            customer_email=current_user.email,
            customer_phone=phone,
            return_url=f"{settings.base_url}/?placeai_payment=1&order_id={order_id}",
            notify_url=f"{settings.base_url}/billing/cashfree/webhook",
            order_note="PlaceAI AI Career Roadmap one-time unlock",
        )
    except CashfreePaymentError as exc:
        raise _payment_http_error(exc) from exc

    pending = StudentFeaturePurchase(
        student_id=profile.id,
        feature_code=CAREER_ROADMAP_FEATURE_CODE,
        status="pending",
        provider=CASHFREE_PROVIDER,
        provider_order_id=order_id,
        amount_paise=CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
    )
    db.add(pending)
    db.commit()
    return _checkout_response(
        provider_order=provider_order,
        settings=settings,
        product=CAREER_ROADMAP_FEATURE_CODE,
        amount_paise=CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
    )


@router.post("/verify/{order_id}")
def verify_checkout(
    order_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.cashfree_checkout_ready:
        raise _checkout_unavailable()
    return _verify_and_activate(db=db, settings=settings, order_id=order_id, expected_user=current_user)


@router.post("/cashfree/webhook")
async def cashfree_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.cashfree_checkout_ready:
        raise _checkout_unavailable()

    raw_body = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    if not verify_webhook_signature(
        raw_body=raw_body,
        timestamp=timestamp,
        signature=signature,
        secret_key=settings.cashfree_secret_key,
    ):
        raise HTTPException(status_code=401, detail={"code": "PAYMENT_WEBHOOK_SIGNATURE_INVALID", "message": "Invalid payment webhook signature."})

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "PAYMENT_WEBHOOK_INVALID", "message": "Invalid payment webhook payload."}) from exc

    event_type = str(payload.get("type") or "").upper() if isinstance(payload, dict) else ""
    if event_type != "PAYMENT_SUCCESS_WEBHOOK":
        return {"accepted": True, "processed": False}

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    order_id = str(order.get("order_id") or "").strip()
    if not order_id:
        raise HTTPException(status_code=400, detail={"code": "PAYMENT_WEBHOOK_ORDER_MISSING", "message": "Payment webhook did not include an order reference."})

    result = _verify_and_activate(db=db, settings=settings, order_id=order_id, expected_user=None)
    return {"accepted": True, "processed": bool(result.get("verified")), **result}
