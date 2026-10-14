"""New-password screening explicitly approved by the owner on 14 October 2026.

Only a five-character SHA-1 prefix is sent to the official HIBP range API.
"""
from __future__ import annotations

import hashlib
import time
from functools import lru_cache

import httpx
from fastapi import HTTPException

from app.config import get_settings


@lru_cache(maxsize=256)
def _range_cached(prefix: str, time_bucket: int) -> tuple[str, ...]:
    with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
        response = client.get(f"https://api.pwnedpasswords.com/range/{prefix}",
                              headers={"Add-Padding": "true", "User-Agent": "PlaceAI-Password-Screening"})
        response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("Invalid password screening response")
    rows = tuple(response.text.splitlines())
    if not rows or any(len(row.partition(":")[0]) != 35 or not row.partition(":")[2].isdigit() for row in rows):
        raise ValueError("Invalid password screening response")
    return rows


def _range(prefix: str) -> tuple[str, ...]:
    return _range_cached(prefix, int(time.time()) // 600)


def screen_new_password(password: str) -> None:
    common = {"password123!", "password1234!", "password12345!", "qwerty123456!", "welcome12345!", "administrator1!"}
    if password.casefold() in common:
        raise HTTPException(422, "This password is commonly used. Choose a unique password or passphrase.")
    if not get_settings().is_production:
        return
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    try:
        rows = _range(digest[:5])
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Password safety check is temporarily unavailable. Please try again.") from None
    for row in rows:
        suffix, _, count = row.partition(":")
        if suffix == digest[5:] and int(count) > 0:
            raise HTTPException(422, "This password appears in known data breaches. Choose a unique password or passphrase.")
