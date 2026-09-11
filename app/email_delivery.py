from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

import httpx

BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


def smtp_transport_configured(settings) -> bool:
    credentials_consistent = bool(settings.smtp_user) == bool(settings.smtp_password)
    return bool(settings.smtp_host and settings.smtp_from and credentials_consistent)


def brevo_api_configured(settings) -> bool:
    return bool(getattr(settings, "brevo_api_key", "") and settings.smtp_from)


def transactional_email_configured(settings) -> bool:
    return smtp_transport_configured(settings) or brevo_api_configured(settings)


def _brevo_api_failure_reason(status_code: int) -> str:
    """Map provider HTTP failures to sanitized operational reason codes."""
    if status_code in {401, 403}:
        return "brevo_api_auth_failed"
    if status_code == 400:
        return "brevo_api_request_rejected"
    if status_code == 429:
        return "brevo_api_rate_limited"
    if 500 <= status_code < 600:
        return "brevo_api_provider_unavailable"
    return "brevo_api_delivery_failed"


def _brevo_headers(settings) -> dict[str, str]:
    return {
        "accept": "application/json",
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
    }


def _plain_body_as_html(body: str) -> str:
    """Convert trusted application plain text into minimal safe HTML for provider fallback."""
    return "<div>" + html.escape(body).replace("\n", "<br>") + "</div>"


def _post_brevo(settings, payload: dict) -> httpx.Response:
    return httpx.post(
        BREVO_TRANSACTIONAL_EMAIL_URL,
        json=payload,
        headers=_brevo_headers(settings),
        timeout=8.0,
    )


def send_transactional_email(settings, *, recipient: str, subject: str, body: str) -> tuple[str, str | None]:
    """Send mail through configured SMTP, with Brevo HTTPS API as a safe fallback.

    Brevo normally accepts a textContent payload with a verified sender. Some account
    configurations reject that otherwise-valid shape with HTTP 400. When that happens,
    PlaceAI retries once with the same verified sender email, no sender-name override,
    and an escaped HTML body. The retry is deliberately limited to request-rejection
    responses so auth, rate-limit and provider failures are never hidden.

    The return value intentionally exposes only sanitized operational outcome codes.
    Secrets, provider response bodies, recipients and exception text must never be persisted.
    """
    recipient = recipient.strip().lower()
    if not recipient:
        return "failed", "recipient_missing"

    smtp_ready = smtp_transport_configured(settings)
    api_ready = brevo_api_configured(settings)
    smtp_failed = False

    if smtp_ready:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings.app_name} <{settings.smtp_from}>"
        message["To"] = recipient
        message.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
                if settings.smtp_tls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
            return "sent", None
        except smtplib.SMTPAuthenticationError:
            smtp_failed = True
            if not api_ready:
                return "failed", "smtp_authentication_failed"
        except (smtplib.SMTPException, OSError):
            smtp_failed = True
            if not api_ready:
                return "failed", "smtp_delivery_failed"
        except Exception:
            smtp_failed = True
            if not api_ready:
                return "failed", "smtp_delivery_failed"

    if api_ready:
        payload = {
            "sender": {"name": settings.app_name, "email": settings.smtp_from},
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": body,
        }
        try:
            response = _post_brevo(settings, payload)
            if 200 <= response.status_code < 300:
                return "sent", None

            if response.status_code == 400:
                compatibility_payload = {
                    "sender": {"email": settings.smtp_from},
                    "to": [{"email": recipient}],
                    "subject": subject,
                    "htmlContent": _plain_body_as_html(body),
                }
                retry = _post_brevo(settings, compatibility_payload)
                if 200 <= retry.status_code < 300:
                    return "sent", None
                return "failed", _brevo_api_failure_reason(retry.status_code)

            return "failed", _brevo_api_failure_reason(response.status_code)
        except httpx.TimeoutException:
            return "failed", "brevo_api_timeout"
        except httpx.HTTPError:
            return "failed", "brevo_api_network_failed"
        except Exception:
            return "failed", "brevo_api_delivery_failed"

    if smtp_failed:
        return "failed", "smtp_delivery_failed"
    return "not_configured", "transactional_email_not_configured"
