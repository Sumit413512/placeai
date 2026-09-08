from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()
password_hash = PasswordHasher()


def get_hashed_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_pass: str) -> bool:
    try:
        return password_hash.verify(hashed_pass, password)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _token(subject: str, secret: str, expires_delta: timedelta, token_type: str, auth_version: int) -> str:
    now = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "type": token_type,
        "ver": int(auth_version),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_urlsafe(18),
    }
    head = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url_encode(signature)}"


def decode_token(token: str, secret: str, expected_type: str) -> dict:
    try:
        head, body, signature = token.split(".")
        header = json.loads(_b64url_decode(head))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("header")
        expected = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            raise ValueError("signature")
        payload = json.loads(_b64url_decode(body))
        if payload.get("type") != expected_type:
            raise ValueError("type")
        now = int(datetime.now(timezone.utc).timestamp())
        exp = int(payload.get("exp", 0))
        iat = int(payload.get("iat", 0))
        if exp <= now or iat > now + 60:
            raise ValueError("time")
        if not payload.get("sub") or not payload.get("jti"):
            raise ValueError("claims")
        if int(payload.get("ver", 0)) < 1:
            raise ValueError("version")
        return payload
    except Exception as exc:
        raise ValueError("Invalid or expired token") from exc


def create_access_token(subject: str, auth_version: int = 1) -> str:
    return _token(subject, settings.jwt_secret_key, timedelta(minutes=settings.access_token_minutes), "access", auth_version)


def create_refresh_token(subject: str, auth_version: int = 1) -> str:
    return _token(subject, settings.jwt_refresh_secret_key, timedelta(days=settings.refresh_token_days), "refresh", auth_version)


def decode_refresh_payload(token: str) -> dict:
    try:
        return decode_token(token, settings.jwt_refresh_secret_key, "refresh")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")


def decode_refresh_token(token: str) -> str:
    return str(decode_refresh_payload(token)["sub"])


def generate_reset_token() -> str:
    return secrets.token_urlsafe(36)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
