from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.models import AuditEvent, StudentProfile, User
from app.roadmap_access import ensure_roadmap_access, roadmap_access_status
from app.roadmap_models import CareerRoadmap
from app.roadmap_service import generate_market_roadmap

router = APIRouter(prefix="/roadmap", tags=["Career Roadmap"])
LOGGER = logging.getLogger("placeai.roadmap")


class CareerRoadmapRequest(BaseModel):
    interests: list[str] = Field(default_factory=list, max_length=12)
    target_roles: list[str] = Field(default_factory=list, max_length=8)
    target_fields: list[str] = Field(default_factory=list, max_length=8)
    current_skills: list[str] = Field(default_factory=list, max_length=40)
    experience_level: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    market_region: str = Field(default="India", min_length=2, max_length=120)
    hours_per_week: int = Field(default=10, ge=1, le=80)
    desired_timeline_days: int | None = Field(default=None, ge=14, le=730)
    learning_style: str | None = Field(default=None, max_length=500)
    goals_constraints: str | None = Field(default=None, max_length=2000)

    @field_validator("interests", "target_roles", "target_fields", "current_skills")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = " ".join(str(raw or "").split())[:180]
            if len(value) < 2 or value.casefold() in seen:
                continue
            seen.add(value.casefold())
            output.append(value)
        return output

    @field_validator("market_region")
    @classmethod
    def clean_region(cls, value: str) -> str:
        return " ".join(value.split())[:120]

    @model_validator(mode="after")
    def require_goal(self):
        if not (self.interests or self.target_roles or self.target_fields):
            raise ValueError("Add at least one interest, target career role, or target field")
        return self


def _profile(current_user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _latest(profile: StudentProfile, db: Session) -> CareerRoadmap | None:
    return (
        db.query(CareerRoadmap)
        .filter(CareerRoadmap.student_id == profile.id)
        .order_by(CareerRoadmap.created_at.desc())
        .first()
    )


def _record_generation_failure(
    db: Session,
    *,
    current_user: User,
    profile: StudentProfile,
    access_source: str,
    market_region: str,
    error_code: str,
    status_code: int,
    primary_code: str | None = None,
    fallback_code: str | None = None,
    gateway_code: str | None = None,
) -> None:
    """Persist only safe operational metadata for failed roadmap generations."""
    try:
        db.rollback()
        audit = AuditEvent(
            actor_user_id=current_user.id,
            organization_id=profile.organization_id or current_user.organization_id,
            action="career_roadmap.generation_failed",
            entity_type="career_roadmap",
        )
        audit.details = {
            "stage": "market_research",
            "error_code": error_code[:120],
            "status_code": int(status_code),
            "market_region": market_region[:120],
            "access_source": access_source[:80],
            "primary_code": (primary_code or "")[:120] or None,
            "fallback_code": (fallback_code or "")[:120] or None,
            "gateway_code": (gateway_code or "")[:120] or None,
        }
        db.add(audit)
        db.commit()
    except Exception:
        db.rollback()
        LOGGER.exception("Career roadmap failure audit could not be persisted")


def _serialize(row: CareerRoadmap) -> dict[str, Any]:
    roadmap = row.roadmap
    return {
        "id": row.id,
        "title": row.title,
        "target_role": row.target_role,
        "target_field": row.target_field,
        "market_region": row.market_region,
        "input": row.request_input,
        "market_snapshot": row.market_snapshot,
        "roadmap": roadmap,
        "sources": row.sources,
        "estimated_days": roadmap.get("estimated_days"),
        "weekly_hours": roadmap.get("weekly_hours"),
        "ai_provider": row.ai_provider,
        "ai_model": row.ai_model,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "disclaimer": roadmap.get("disclaimer"),
    }


@router.get("/status")
def roadmap_status(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    access = roadmap_access_status(current_user, db)
    latest = _latest(profile, db)
    return {
        **access,
        "latest_available": latest is not None,
        "latest": {
            "id": latest.id,
            "title": latest.title,
            "created_at": latest.created_at,
            "market_region": latest.market_region,
        } if latest else None,
    }


@router.get("/latest")
def latest_roadmap(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    ensure_roadmap_access(current_user, db)
    profile = _profile(current_user, db)
    row = _latest(profile, db)
    if not row:
        raise HTTPException(status_code=404, detail="No career roadmap has been generated yet")
    return _serialize(row)


@router.get("/history")
def roadmap_history(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    ensure_roadmap_access(current_user, db)
    profile = _profile(current_user, db)
    rows = (
        db.query(CareerRoadmap)
        .filter(CareerRoadmap.student_id == profile.id)
        .order_by(CareerRoadmap.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "target_role": row.target_role,
            "target_field": row.target_field,
            "market_region": row.market_region,
            "estimated_days": row.roadmap.get("estimated_days"),
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/generate", dependencies=[Depends(student_ai_guard)])
def generate_roadmap(
    request: CareerRoadmapRequest,
    http_request: Request,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    access = ensure_roadmap_access(current_user, db)
    profile = _profile(current_user, db)
    request_data = request.model_dump()
    LOGGER.info(
        "Career roadmap generation started access_source=%s region=%s target_role_present=%s",
        access["access_source"],
        request.market_region,
        bool(request.target_roles),
    )
    try:
        roadmap, sources, model = generate_market_roadmap(
            db=db,
            profile=profile,
            request_data=request_data,
            gateway_token=http_request.headers.get("x-vercel-oidc-token"),
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        diagnostics = detail.pop("diagnostics", {}) if isinstance(detail, dict) else {}
        code = str(detail.get("code") or "CAREER_ROADMAP_GENERATION_FAILED")
        primary_code = str(diagnostics.get("primary_code") or "") or None if isinstance(diagnostics, dict) else None
        fallback_code = str(diagnostics.get("fallback_code") or "") or None if isinstance(diagnostics, dict) else None
        gateway_code = str(diagnostics.get("gateway_code") or "") or None if isinstance(diagnostics, dict) else None
        LOGGER.warning(
            "Career roadmap generation stopped stage=market_research status_code=%s error_code=%s "
            "primary_code=%s fallback_code=%s gateway_code=%s",
            exc.status_code,
            code,
            primary_code,
            fallback_code,
            gateway_code,
        )
        _record_generation_failure(
            db,
            current_user=current_user,
            profile=profile,
            access_source=str(access["access_source"]),
            market_region=request.market_region,
            error_code=code,
            status_code=exc.status_code,
            primary_code=primary_code,
            fallback_code=fallback_code,
            gateway_code=gateway_code,
        )
        raise
    except Exception:
        LOGGER.exception("Career roadmap generation stopped stage=market_research error_code=UNEXPECTED_FAILURE")
        _record_generation_failure(
            db,
            current_user=current_user,
            profile=profile,
            access_source=str(access["access_source"]),
            market_region=request.market_region,
            error_code="UNEXPECTED_FAILURE",
            status_code=500,
        )
        raise

    LOGGER.info(
        "Career roadmap market research completed model=%s source_count=%s phase_count=%s",
        model,
        len(sources),
        len(roadmap.get("phases") or []),
    )

    row = CareerRoadmap(
        student_id=profile.id,
        title=roadmap["title"],
        target_role=request.target_roles[0] if request.target_roles else None,
        target_field=request.target_fields[0] if request.target_fields else None,
        market_region=request.market_region,
        ai_provider=(
            "vercel_ai_gateway"
            if str(model).lower().startswith("gateway:")
            else ("gemini" if str(model).lower().startswith("gemini") else "openai")
        ),
        ai_model=str(model).removeprefix("gateway:"),
    )
    row.request_input = request_data
    row.market_snapshot = roadmap["market_snapshot"]
    row.roadmap = roadmap
    row.sources = sources
    db.add(row)
    db.flush()

    audit = AuditEvent(
        actor_user_id=current_user.id,
        organization_id=profile.organization_id or current_user.organization_id,
        action="career_roadmap.generated",
        entity_type="career_roadmap",
        entity_id=row.id,
    )
    audit.details = {
        "market_region": request.market_region,
        "target_role": row.target_role,
        "target_field": row.target_field,
        "source_count": len(sources),
        "access_source": access["access_source"],
    }
    db.add(audit)
    db.commit()
    db.refresh(row)
    LOGGER.info(
        "Career roadmap generation completed model=%s source_count=%s",
        model,
        len(sources),
    )
    return _serialize(row)
