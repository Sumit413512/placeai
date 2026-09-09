from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RateLimitBucket

settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_address(request: Request) -> str:
    # Vercel supplies the forwarding chain. Outside Vercel, trust the ASGI peer instead
    # of arbitrary forwarded headers from clients.
    if settings.running_on_vercel:
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:80]
    if request.client and request.client.host:
        return request.client.host[:80]
    return "unknown"


def _bucket_key(
    request: Request,
    scope: str,
    identifier: str | None,
    *,
    include_client_address: bool = True,
) -> str:
    client_component = _client_address(request) if include_client_address else "account"
    raw = f"{scope}|{client_component}|{(identifier or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enforce_rate_limit(
    db: Session,
    request: Request,
    *,
    scope: str,
    identifier: str | None = None,
    limit: int,
    window_seconds: int,
    block_seconds: int | None = None,
    include_client_address: bool = True,
) -> None:
    """Durable fixed-window limiter suitable for multi-instance deployments.

    By default the deterministic SHA-256 key includes scope, client address and
    identifier, preserving the existing auth/abuse throttling semantics without storing
    raw email/IP values. Authenticated account budgets can explicitly disable the client
    component so changing IP does not create a fresh quota.
    """
    now = _utcnow()
    key_hash = _bucket_key(
        request,
        scope,
        identifier,
        include_client_address=include_client_address,
    )
    bucket = (
        db.query(RateLimitBucket)
        .filter(RateLimitBucket.key_hash == key_hash)
        .with_for_update()
        .first()
    )

    if bucket and bucket.blocked_until and bucket.blocked_until > now:
        retry_after = max(1, int((bucket.blocked_until - now).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not bucket:
        bucket = RateLimitBucket(
            key_hash=key_hash,
            scope=scope[:80],
            window_started_at=now,
            request_count=1,
            updated_at=now,
        )
        db.add(bucket)
        try:
            db.commit()
            return
        except IntegrityError:
            # Another instance may have created the same deterministic bucket between
            # our SELECT and INSERT. Roll back and continue against that row instead
            # of surfacing a transient 500.
            db.rollback()
            bucket = (
                db.query(RateLimitBucket)
                .filter(RateLimitBucket.key_hash == key_hash)
                .with_for_update()
                .first()
            )
            if not bucket:
                raise

    elapsed = (now - bucket.window_started_at).total_seconds()
    if elapsed >= window_seconds:
        bucket.window_started_at = now
        bucket.request_count = 1
        bucket.blocked_until = None
        bucket.updated_at = now
        db.commit()
        return

    bucket.request_count += 1
    bucket.updated_at = now
    if bucket.request_count > limit:
        seconds = block_seconds if block_seconds is not None else max(60, window_seconds)
        bucket.blocked_until = now + timedelta(seconds=seconds)
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(seconds)},
        )
    db.commit()
