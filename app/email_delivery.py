from __future__ import annotations

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


def send_transactional_email(settings, *, recipient: str, subject: str, body: str) -> tuple[str, str | None]:
    """Send mail through configured SMTP, with Brevo HTTPS API as a safe fallback.

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
            response = httpx.post(
                BREVO_TRANSACTIONAL_EMAIL_URL,
                json=payload,
                headers={
                    "accept": "application/json",
                    "api-key": settings.brevo_api_key,
                    "content-type": "application/json",
                },
                timeout=8.0,
            )
            if 200 <= response.status_code < 300:
                return "sent", None
            return "failed", "brevo_api_delivery_failed"
        except httpx.HTTPError:
            return "failed", "brevo_api_delivery_failed"
        except Exception:
            return "failed", "brevo_api_delivery_failed"

    if smtp_failed:
        return "failed", "smtp_delivery_failed"
    return "not_configured", "transactional_email_not_configured"
