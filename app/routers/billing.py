from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_student
from app.models import IndividualStudentAccess, PaymentTransaction, User
from app.placement_access import utcnow_naive
from app.student_access import (
    INDIVIDUAL_PLAN_CODE,
    get_or_create_individual_access,
    is_university_student,
    refresh_individual_status,
    student_access_payload,
)

settings = get_settings()
router = APIRouter(prefix="/billing", tags=["Student Billing"])

RAZORPAY_API = "https://api.razorpay.com/v1"
ACCESS_DAYS_PER_PAYMENT = 30


class PaymentVerificationIn(BaseModel):
    razorpay_order_id: str = Field(min_length=5, max_length=180)
    razorpay_payment_id: str = Field(min_length=5, max_length=180)
    razorpay_signature: str = Field(min_length=32, max_length=256)


def _gateway_ready() -> bool:
    return (
        settings.student_payment_provider == "razorpay"
        and bool(settings.razorpay_key_id)
        and bool(settings.razorpay_key_secret)
    )


def _plan_payload() -> dict:
    amount_inr = settings.student_individual_monthly_price_inr
    return {
        "code": INDIVIDUAL_PLAN_CODE,
        "name": "PlaceAI Individual Pro",
        "price_inr": amount_inr,
        "amount_paise": amount_inr * 100,
        "currency": "INR",
        "access_days": ACCESS_DAYS_PER_PAYMENT,
        "trial_days": settings.student_individual_trial_days,
        "payment_methods": ["UPI", "cards", "netbanking", "wallets"],
        "provider": "razorpay" if settings.student_payment_provider == "razorpay" else "pending_selection",
        "checkout_available": _gateway_ready(),
    }


def _razorpay_request(method: str, path: str, *, json_body: dict | None = None) -> dict[str, Any]:
    if not _gateway_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PAYMENT_GATEWAY_NOT_CONFIGURED",
                "message": "Individual Pro billing is prepared, but the live payment gateway has not been activated yet.",
            },
        )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        ) as client:
            response = client.request(method, f"{RAZORPAY_API}{path}", json=json_body)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PAYMENT_PROVIDER_UNAVAILABLE", "message": "Payment provider is temporarily unavailable."},
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PAYMENT_PROVIDER_ERROR", "message": "Payment provider rejected the request."},
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PAYMENT_PROVIDER_INVALID_RESPONSE", "message": "Payment provider returned an invalid response."},
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Payment provider returned an invalid response")
    return payload


def _activate_transaction(
    db: Session,
    transaction: PaymentTransaction,
    payment_id: str,
) -> IndividualStudentAccess:
    access = (
        db.query(IndividualStudentAccess)
        .filter(IndividualStudentAccess.id == transaction.individual_access_id)
        .with_for_update()
        .first()
    )
    if not access:
        raise HTTPException(status_code=409, detail="Individual access record is unavailable")

    # Idempotency: a repeated verified callback must never extend access twice.
    if transaction.status == "paid" and transaction.provider_payment_id == payment_id:
        return access

    now = utcnow_naive()
    base = access.paid_access_until if access.paid_access_until and access.paid_access_until > now else now
    access.paid_access_until = base + timedelta(days=ACCESS_DAYS_PER_PAYMENT)
    access.status = "active"
    access.payment_provider = "razorpay"
    transaction.provider_payment_id = payment_id
    transaction.status = "paid"
    transaction.updated_at = now
    access.updated_at = now
    db.commit()
    db.refresh(access)
    return access


@router.get("/student/status")
def student_billing_status(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    payload = student_access_payload(current_user, db)
    payload["billing"] = _plan_payload()
    return payload


@router.get("/student/plans")
def student_plans(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    if is_university_student(current_user, db):
        return {
            "account_type": "university",
            "payment_required": False,
            "plans": [],
            "message": "University-associated student access is included and is not billed individually.",
        }
    return {"account_type": "individual", "payment_required": True, "plans": [_plan_payload()]}


@router.post("/student/checkout")
def create_student_checkout(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    if is_university_student(current_user, db):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "UNIVERSITY_ACCESS_INCLUDED",
                "message": "University-associated students are not charged for PlaceAI student access.",
            },
        )

    access = get_or_create_individual_access(current_user, db)
    refresh_individual_status(access, db)
    plan = _plan_payload()
    if not plan["checkout_available"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PAYMENT_GATEWAY_NOT_CONFIGURED",
                "message": "The Individual Pro plan is ready, but live payment acceptance is not enabled yet.",
                "plan": plan,
            },
        )

    transaction = PaymentTransaction(
        user_id=current_user.id,
        individual_access_id=access.id,
        provider="razorpay",
        amount_paise=plan["amount_paise"],
        currency="INR",
        status="creating",
    )
    db.add(transaction)
    db.flush()

    order = _razorpay_request(
        "POST",
        "/orders",
        json_body={
            "amount": plan["amount_paise"],
            "currency": "INR",
            "receipt": f"placeai_{transaction.id.replace('-', '')[:24]}",
            "notes": {
                "placeai_user_id": current_user.id,
                "plan_code": INDIVIDUAL_PLAN_CODE,
            },
        },
    )
    order_id = str(order.get("id") or "").strip()
    if not order_id:
        db.rollback()
        raise HTTPException(status_code=502, detail="Payment provider did not return an order id")

    transaction.provider_order_id = order_id
    transaction.status = "created"
    db.commit()

    return {
        "provider": "razorpay",
        "key_id": settings.razorpay_key_id,
        "order_id": order_id,
        "amount_paise": plan["amount_paise"],
        "currency": "INR",
        "plan": plan,
        "prefill": {"email": current_user.email},
        "notes": {"plan_code": INDIVIDUAL_PLAN_CODE},
    }


@router.post("/student/verify")
def verify_student_payment(
    body: PaymentVerificationIn,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    if not _gateway_ready():
        raise HTTPException(status_code=503, detail="Payment gateway is not configured")
    if is_university_student(current_user, db):
        raise HTTPException(status_code=409, detail="University-associated students do not require individual billing")

    transaction = db.query(PaymentTransaction).filter(
        PaymentTransaction.user_id == current_user.id,
        PaymentTransaction.provider == "razorpay",
        PaymentTransaction.provider_order_id == body.razorpay_order_id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Payment order not found")

    expected = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    payment = _razorpay_request("GET", f"/payments/{body.razorpay_payment_id}")
    if str(payment.get("order_id") or "") != body.razorpay_order_id:
        raise HTTPException(status_code=409, detail="Payment does not belong to this order")
    if int(payment.get("amount") or 0) != transaction.amount_paise or str(payment.get("currency") or "") != "INR":
        raise HTTPException(status_code=409, detail="Payment amount or currency does not match the PlaceAI order")
    if str(payment.get("status") or "").lower() != "captured":
        raise HTTPException(
            status_code=409,
            detail="Payment is not captured yet. Access will unlock only after captured payment is verified.",
        )

    access = _activate_transaction(db, transaction, body.razorpay_payment_id)
    payload = student_access_payload(current_user, db)
    payload["paid_access_until"] = access.paid_access_until
    return payload


@router.post("/razorpay/webhook", status_code=204)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=503, detail="Payment webhook is not configured")

    raw = await request.body()
    provided = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()
    if not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    event = str(payload.get("event") or "")
    if event not in {"payment.captured", "order.paid"}:
        return

    payment = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
    payment_id = str(payment.get("id") or "")
    order_id = str(payment.get("order_id") or "")
    if not payment_id or not order_id:
        return

    transaction = db.query(PaymentTransaction).filter(
        PaymentTransaction.provider == "razorpay",
        PaymentTransaction.provider_order_id == order_id,
    ).first()
    if not transaction:
        return

    if int(payment.get("amount") or 0) != transaction.amount_paise or str(payment.get("currency") or "") != transaction.currency:
        raise HTTPException(status_code=409, detail="Webhook payment does not match the recorded PlaceAI order")
    if str(payment.get("status") or "").lower() != "captured":
        return

    _activate_transaction(db, transaction, payment_id)
