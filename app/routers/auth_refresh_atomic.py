from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RefreshSession, User
from app.rate_limit import enforce_rate_limit
from app.routers.auth import COOKIE_NAME, _token_response, _utcnow
from app.schemas import RefreshTokenRequest, TokenSchema
from app.utils import decode_refresh_payload

router = APIRouter(tags=["Authentication"])


@router.post("/auth/refresh", response_model=TokenSchema)
def refresh_token_atomic(
    body: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate a refresh token exactly once, including under concurrent requests.

    The refresh-session row is locked until `_token_response` revokes the current JTI,
    creates its successor and commits. A concurrent request using the same token blocks
    on this row; after the first rotation commits it observes `revoked_at` and is denied.
    """
    enforce_rate_limit(db, request, scope="refresh", limit=60, window_seconds=600, block_seconds=600)
    token = body.refresh_token or request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    payload = decode_refresh_payload(token)
    email = str(payload["sub"])
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or int(payload.get("ver", 0)) != int(user.auth_version or 1):
        raise HTTPException(status_code=401, detail="Account session is unavailable")

    session = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.jti == str(payload["jti"]),
            RefreshSession.user_id == user.id,
        )
        .with_for_update()
        .first()
    )
    if (
        not session
        or session.revoked_at is not None
        or session.expires_at <= _utcnow()
        or session.auth_version != int(user.auth_version or 1)
    ):
        raise HTTPException(status_code=401, detail="Refresh session is invalid or revoked")

    return _token_response(user, response, db, revoke_jti=session.jti)
