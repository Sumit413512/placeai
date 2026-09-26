from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_institution_admin, require_student
from app.models import Organization, PlacementAction, StudentProfile, User
from app.product_intelligence import (
    institution_action_centre,
    readiness_evidence,
    student_next_actions,
    sync_placement_actions,
    utcnow,
)
from app.services import record_audit
from app.student_entitlements import require_student_premium_access

router = APIRouter(prefix="/intelligence", tags=["Placement Intelligence"])


class PlacementActionUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved", "dismissed"]
    resolution_note: str | None = Field(default=None, max_length=1000)


def _organization_for_admin(user: User, db: Session) -> Organization:
    if not user.organization_id:
        raise HTTPException(status_code=403, detail="Account is not linked to an institution")
    org = db.query(Organization).filter(
        Organization.id == user.organization_id,
        Organization.is_active.is_(True),
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Institution is inactive or unavailable")
    return org


def _student_for_user(user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


@router.get("/student/actions")
def student_actions(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = _student_for_user(current_user, db)
    return {
        "actions": student_next_actions(student, db),
        "generated_at": utcnow().isoformat(),
        "disclaimer": "Next actions are based on recorded profile, eligibility, deadline and preparation evidence. They do not guarantee placement outcomes.",
    }


@router.get("/student/readiness")
def student_readiness_evidence(
    current_user: User = Depends(require_student_premium_access),
    db: Session = Depends(get_db),
):
    return readiness_evidence(_student_for_user(current_user, db), db)


@router.post("/institution/actions/sync")
def sync_actions(
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _organization_for_admin(current_user, db)
    result = sync_placement_actions(org.id, db)
    record_audit(
        db,
        current_user,
        "institution.placement_actions.synced",
        organization_id=org.id,
        entity_type="placement_action",
        metadata=result,
    )
    db.commit()
    return result


@router.get("/institution/actions")
def institution_actions(
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _organization_for_admin(current_user, db)
    return institution_action_centre(org.id, db)


@router.patch("/institution/actions/{action_id}")
def update_action(
    action_id: str,
    payload: PlacementActionUpdate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _organization_for_admin(current_user, db)
    row = db.query(PlacementAction).filter(
        PlacementAction.id == action_id,
        PlacementAction.organization_id == org.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Placement action not found")
    previous_status = row.status
    row.status = payload.status
    row.resolution_note = (payload.resolution_note or "").strip() or None
    if payload.status == "in_progress":
        row.owner_user_id = current_user.id
        row.resolved_at = None
        row.resolution_outcome = None
    elif payload.status in {"resolved", "dismissed"}:
        row.owner_user_id = row.owner_user_id or current_user.id
        row.resolved_at = utcnow()
        row.resolution_outcome = "human_resolved" if payload.status == "resolved" else "human_dismissed"
    else:
        row.resolved_at = None
        row.resolution_outcome = None
    record_audit(
        db,
        current_user,
        "institution.placement_action.status_changed",
        organization_id=org.id,
        entity_type="placement_action",
        entity_id=row.id,
        metadata={"previous_status": previous_status, "status": row.status},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "status": row.status,
        "owner_user_id": row.owner_user_id,
        "resolved_at": row.resolved_at.isoformat() if isinstance(row.resolved_at, datetime) else None,
        "resolution_outcome": row.resolution_outcome,
    }
