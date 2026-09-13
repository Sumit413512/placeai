from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RefreshSession, User
from app.rate_limit import enforce_rate_limit
from app.routers.auth import _token_response, _utcnow
from app.schemas import TokenSchema, _strong_password
from app.utils import get_hashed_password, verify_password

router = APIRouter(tags=["Account security"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _strong_password(value)


@router.post("/auth/change-password", response_model=TokenSchema)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atomically rotate a password and invalidate every pre-rotation session."""
    enforce_rate_limit(
        db,
        request,
        scope="change-password",
        identifier=current_user.email,
        limit=8,
        window_seconds=900,
        block_seconds=1800,
        include_client_address=False,
    )

    # Serialize password changes for one account. Without this lock, concurrent requests
    # can both validate the same previous password and the final commit becomes
    # last-writer-wins. The locked re-read makes the second request observe the first
    # rotation and fail its current-password check.
    locked_user = (
        db.query(User)
        .filter(User.id == current_user.id, User.is_active.is_(True))
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not locked_user:
        raise HTTPException(status_code=401, detail="Account session is unavailable")
    if not verify_password(body.current_password, locked_user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if verify_password(body.new_password, locked_user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    now = _utcnow()
    locked_user.hashed_password = get_hashed_password(body.new_password)
    locked_user.must_change_password = False
    locked_user.reset_token_hash = None
    locked_user.reset_token_expires = None
    locked_user.auth_version = int(locked_user.auth_version or 1) + 1
    db.query(RefreshSession).filter(
        RefreshSession.user_id == locked_user.id,
        RefreshSession.revoked_at.is_(None),
    ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    db.commit()
    db.refresh(locked_user)
    return _token_response(locked_user, response, db)
