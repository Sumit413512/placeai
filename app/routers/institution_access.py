from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.access_models import AccessRequest
from app.access_request_guards import ensure_manual_access_status
from app.database import get_db
from app.dependencies import require_institution_admin
from app.models import User
from app.routers.auth import _utcnow
from app.routers.institution_secure import _org
from app.services import record_audit

router = APIRouter(prefix="/institutions", tags=["Institution / TPO"])


def _institution_request_scope(query, org):
    normalized_name = func.lower(func.trim(org.name))
    normalized_slug = func.lower(func.trim(org.slug))
    normalized_request_org = func.lower(func.trim(AccessRequest.organization_name))
    return query.filter(
        AccessRequest.requested_role == "recruiter",
        or_(
            AccessRequest.organization_id == org.id,
            and_(
                AccessRequest.organization_id.is_(None),
                AccessRequest.organization_name.is_not(None),
                or_(
                    normalized_request_org == normalized_name,
                    normalized_request_org == normalized_slug,
                ),
            ),
        ),
    )


def _payload(row: AccessRequest) -> dict:
    return {
        "id": row.id,
        "requested_role": row.requested_role,
        "full_name": row.full_name,
        "work_email": row.work_email,
        "organization_name": row.organization_name,
        "organization_id": row.organization_id,
        "phone": row.phone,
        "message": row.message,
        "status": row.status,
        "review_note": row.review_note,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/access-requests")
def institution_access_requests(
    request_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Return only recruiter access requests belonging to the signed-in institution."""
    org = _org(current_user, db)
    query = _institution_request_scope(db.query(AccessRequest), org)
    if request_status:
        if request_status not in {"new", "under_review", "approved", "rejected", "provisioned"}:
            raise HTTPException(status_code=422, detail="Invalid access request status")
        query = query.filter(AccessRequest.status == request_status)
    rows = query.order_by(AccessRequest.created_at.desc()).limit(limit).all()
    return [_payload(row) for row in rows]


@router.patch("/access-requests/{request_id}")
def review_institution_access_request(
    request_id: str,
    body: dict,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org(current_user, db)
    item = _institution_request_scope(
        db.query(AccessRequest).filter(AccessRequest.id == request_id),
        org,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Access request not found")

    requested_status = str(body.get("status") or "").strip()
    next_status = ensure_manual_access_status(requested_status)
    review_note_raw = body.get("review_note")
    review_note = str(review_note_raw).strip() if review_note_raw is not None else None
    if review_note and len(review_note) > 3000:
        raise HTTPException(status_code=422, detail="Review note is too long")

    previous_status = item.status
    previous_note = item.review_note
    item.status = next_status
    item.review_note = review_note or None
    item.reviewed_by_user_id = current_user.id
    item.updated_at = _utcnow()

    if previous_status != item.status or previous_note != item.review_note:
        record_audit(
            db,
            current_user,
            "institution.access_request.reviewed",
            organization_id=org.id,
            entity_type="access_request",
            entity_id=item.id,
            metadata={
                "requested_role": item.requested_role,
                "previous_status": previous_status,
                "status": item.status,
            },
        )

    db.commit()
    db.refresh(item)
    return _payload(item)
