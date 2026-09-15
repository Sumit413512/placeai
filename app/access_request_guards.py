from __future__ import annotations

from typing import Final

from fastapi import HTTPException

MANUAL_ACCESS_STATUSES: Final[frozenset[str]] = frozenset({"new", "under_review", "approved", "rejected"})
ACTIVE_ACCESS_STATUSES: Final[frozenset[str]] = frozenset({"new", "under_review", "approved", "provisioned"})


def normalize_access_request_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 2:
        raise ValueError("Full name must contain at least 2 non-whitespace characters")
    return normalized


def ensure_manual_access_status(status: str) -> str:
    if status not in MANUAL_ACCESS_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Provisioned status is system-managed and can only be set by a provisioning workflow",
        )
    return status
