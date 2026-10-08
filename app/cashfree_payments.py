from __future__ import annotations

import base64
import hashlib
import hmac
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import httpx


CASHFREE_PROVIDER = "cashfree"
CASHFREE_CURRENCY = "INR"
CASHFREE_API_VERSION_DEFAULT = "2025-01-01"


class CashfreePaymentError(RuntimeError):
    """Raised for payment-provider transport or protocol failures."""

    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def amount_to_paise(value: Any) -> int:
    """Convert a provider amount to integer paise without float rounding errors."""
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CashfreePaymentError("PAYMENT_AMOUNT_INVALID", "Payment provider returned an invalid amount.") from exc
    return int((decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def verify_webhook_signature(*, raw_body: bytes, timestamp: str, signature: str, secret_key: str) -> bool:
    """Verify Cashfree's HMAC-SHA256 webhook signature using the unmodified request body."""
    if not raw_body or not timestamp or not signature or not secret_key:
        return False
    signed_payload = timestamp.encode("utf-8") + raw_body
    digest = hmac.new(secret_key.encode("utf-8"), signed_payload, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


class CashfreeClient:
    def __init__(
        self,
        *,
        app_id: str,
        secret_key: str,
        environment: str,
        api_version: str = CASHFREE_API_VERSION_DEFAULT,
        timeout_seconds: int = 15,
    ) -> None:
        self.app_id = app_id.strip()
        self.secret_key = secret_key.strip()
        self.environment = environment.strip().lower()
        self.api_version = api_version.strip() or CASHFREE_API_VERSION_DEFAULT
        self.timeout_seconds = max(5, min(int(timeout_seconds), 60))
        if self.environment not in {"sandbox", "production"}:
            raise ValueError("Cashfree environment must be sandbox or production")
        self.base_url = "https://api.cashfree.com" if self.environment == "production" else "https://sandbox.cashfree.com"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-client-id": self.app_id,
            "x-client-secret": self.secret_key,
            "x-api-version": self.api_version,
        }

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, f"{self.base_url}{path}", headers=self.headers, json=json)
        except httpx.TimeoutException as exc:
            raise CashfreePaymentError("PAYMENT_PROVIDER_TIMEOUT", "Payment provider did not respond in time.", status_code=503) from exc
        except httpx.HTTPError as exc:
            raise CashfreePaymentError("PAYMENT_PROVIDER_NETWORK", "Payment provider could not be reached.", status_code=503) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code >= 400:
            provider_code = payload.get("code") if isinstance(payload, dict) else None
            code = "PAYMENT_PROVIDER_REJECTED"
            if response.status_code in {401, 403}:
                code = "PAYMENT_PROVIDER_AUTH"
            elif response.status_code == 429:
                code = "PAYMENT_PROVIDER_BUSY"
            message = "Payment provider rejected the request."
            if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                message = payload["message"][:300]
            if provider_code:
                message = f"{message} ({provider_code})"
            raise CashfreePaymentError(code, message, status_code=503 if response.status_code >= 500 else 502)

        if payload is None:
            raise CashfreePaymentError("PAYMENT_PROVIDER_RESPONSE_INVALID", "Payment provider returned an invalid response.")
        return payload

    def create_order(
        self,
        *,
        order_id: str,
        amount_paise: int,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        return_url: str,
        notify_url: str,
        order_note: str,
    ) -> dict[str, Any]:
        body = {
            "order_id": order_id,
            "order_amount": float(Decimal(amount_paise) / Decimal("100")),
            "order_currency": CASHFREE_CURRENCY,
            "customer_details": {
                "customer_id": customer_id,
                "customer_email": customer_email,
                "customer_phone": customer_phone,
            },
            "order_meta": {
                "return_url": return_url,
                "notify_url": notify_url,
            },
            "order_note": order_note[:200],
        }
        payload = self._request("POST", "/pg/orders", json=body)
        if not isinstance(payload, dict) or not payload.get("payment_session_id") or payload.get("order_id") != order_id:
            raise CashfreePaymentError("PAYMENT_PROVIDER_RESPONSE_INVALID", "Payment provider did not return a usable checkout session.")
        return payload

    def get_order(self, order_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/pg/orders/{order_id}")
        if not isinstance(payload, dict):
            raise CashfreePaymentError("PAYMENT_PROVIDER_RESPONSE_INVALID", "Payment provider returned an invalid order response.")
        return payload

    def get_order_payments(self, order_id: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/pg/orders/{order_id}/payments")
        if not isinstance(payload, list):
            raise CashfreePaymentError("PAYMENT_PROVIDER_RESPONSE_INVALID", "Payment provider returned an invalid payment response.")
        return [item for item in payload if isinstance(item, dict)]


def successful_payment(payments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for payment in payments:
        if str(payment.get("payment_status") or "").upper() == "SUCCESS":
            return payment
    return None
