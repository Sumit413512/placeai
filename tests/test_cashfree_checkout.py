from __future__ import annotations

import base64
import hashlib
import hmac
from pathlib import Path

import pytest

from app.cashfree_payments import amount_to_paise, successful_payment, verify_webhook_signature
from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]
APP_STATIC = ROOT / "app" / "static"
PUBLIC_STATIC = ROOT / "public" / "static"


def test_cashfree_amount_conversion_is_exact() -> None:
    assert amount_to_paise("20.00") == 2000
    assert amount_to_paise("299.00") == 29900
    assert amount_to_paise("1.235") == 124


def test_cashfree_webhook_signature_uses_timestamp_plus_raw_body() -> None:
    raw = b'{"type":"PAYMENT_SUCCESS_WEBHOOK","data":{"order":{"order_id":"pai_test"}}}'
    timestamp = "1791447000000"
    secret = "test-secret"
    digest = hmac.new(secret.encode(), timestamp.encode() + raw, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()

    assert verify_webhook_signature(raw_body=raw, timestamp=timestamp, signature=signature, secret_key=secret)
    assert not verify_webhook_signature(raw_body=raw + b" ", timestamp=timestamp, signature=signature, secret_key=secret)


def test_successful_payment_only_accepts_success_state() -> None:
    payments = [
        {"payment_status": "FAILED", "cf_payment_id": "1"},
        {"payment_status": "PENDING", "cf_payment_id": "2"},
        {"payment_status": "SUCCESS", "cf_payment_id": "3"},
    ]
    assert successful_payment(payments)["cf_payment_id"] == "3"
    assert successful_payment(payments[:2]) is None


def test_checkout_is_fail_closed_without_explicit_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "PAYMENT_CHECKOUT_ENABLED",
        "CASHFREE_APP_ID",
        "CASHFREE_CLIENT_ID",
        "CASHFREE_SECRET_KEY",
        "CASHFREE_CLIENT_SECRET",
        "CASHFREE_ENVIRONMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    settings = Settings()
    assert settings.payment_provider == "cashfree"
    assert settings.payment_checkout_enabled is False
    assert settings.cashfree_checkout_ready is False


def test_checkout_requires_credentials_and_blocks_sandbox_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYMENT_CHECKOUT_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "cashfree")
    monkeypatch.setenv("CASHFREE_APP_ID", "app-id")
    monkeypatch.setenv("CASHFREE_SECRET_KEY", "secret-key")
    monkeypatch.setenv("CASHFREE_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings()
    assert settings.cashfree_checkout_ready is False
    assert "CASHFREE_SANDBOX_NOT_ALLOWED" in settings.configuration_error_codes()


def test_payment_runtime_is_mirrored_and_loaded_fail_closed() -> None:
    app_runtime = (APP_STATIC / "payment-checkout.js").read_text(encoding="utf-8")
    public_runtime = (PUBLIC_STATIC / "payment-checkout.js").read_text(encoding="utf-8")
    app_loader = (APP_STATIC / "legal-links.js").read_text(encoding="utf-8")
    public_loader = (PUBLIC_STATIC / "legal-links.js").read_text(encoding="utf-8")

    assert app_runtime == public_runtime
    assert app_loader == public_loader
    assert "/static/payment-checkout.js" in app_loader
    assert "sdk.cashfree.com/js/v3/cashfree.js" in app_runtime
    assert "/billing/verify/" in app_runtime
    assert "roadmap_checkout_enabled" in app_runtime
    assert "Fail closed" in app_runtime
