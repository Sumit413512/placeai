from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_recruiter, require_student
from app.models import User
from app.rate_limit import enforce_rate_limit

AI_AGGREGATE_LIMIT_PER_HOUR = 60
AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN = 12
AI_RECRUITER_ENDPOINT_LIMIT_PER_10_MIN = 8
AI_AUTHENTICATED_ENDPOINT_LIMIT_PER_10_MIN = 15


def _enforce_ai_budget(
    request: Request,
    db: Session,
    current_user: User,
    *,
    endpoint_limit: int,
) -> None:
    """Apply durable per-user AI budgets before a cost-generating model call.

    The underlying limiter also includes the client address in its SHA-256 bucket key,
    while `current_user.id` prevents unrelated users behind a campus NAT from sharing
    the same quota. The aggregate bucket caps total model usage across AI features and
    the endpoint bucket suppresses rapid repetition of one expensive operation.
    """
    identifier = current_user.id
    enforce_rate_limit(
        db,
        request,
        scope="ai:aggregate",
        identifier=identifier,
        limit=AI_AGGREGATE_LIMIT_PER_HOUR,
        window_seconds=3600,
        block_seconds=900,
    )
    path_scope = f"ai:{request.url.path}"[:80]
    enforce_rate_limit(
        db,
        request,
        scope=path_scope,
        identifier=identifier,
        limit=endpoint_limit,
        window_seconds=600,
        block_seconds=600,
    )


def student_ai_guard(
    request: Request,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> None:
    _enforce_ai_budget(
        request,
        db,
        current_user,
        endpoint_limit=AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
    )


def recruiter_ai_guard(
    request: Request,
    current_user: User = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> None:
    _enforce_ai_budget(
        request,
        db,
        current_user,
        endpoint_limit=AI_RECRUITER_ENDPOINT_LIMIT_PER_10_MIN,
    )


def authenticated_ai_guard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _enforce_ai_budget(
        request,
        db,
        current_user,
        endpoint_limit=AI_AUTHENTICATED_ENDPOINT_LIMIT_PER_10_MIN,
    )
