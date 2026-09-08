from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DemoRequest
from app.rate_limit import enforce_rate_limit
from app.schemas import DemoRequestCreate, DemoRequestOut

router = APIRouter(prefix="/public", tags=["Public"])


@router.post("/demo-requests", response_model=DemoRequestOut, status_code=status.HTTP_201_CREATED)
def create_demo_request(data: DemoRequestCreate, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope="demo-request", identifier=str(data.work_email), limit=5, window_seconds=3600, block_seconds=3600)
    # Lightweight spam trap. Legitimate clients never see or fill this field.
    # Return a synthetic accepted object instead of revealing the trap behavior.
    if data.website:
        lead = DemoRequest(
            contact_name=data.contact_name,
            work_email=str(data.work_email).lower(),
            organization_name=data.organization_name,
            role_title=data.role_title,
            phone=data.phone,
            student_count=data.student_count,
            message="Spam trap triggered; not a valid sales lead.",
            status="lost",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead

    lead = DemoRequest(
        contact_name=data.contact_name.strip(),
        work_email=str(data.work_email).lower(),
        organization_name=data.organization_name.strip(),
        role_title=data.role_title.strip() if data.role_title else None,
        phone=data.phone.strip() if data.phone else None,
        student_count=data.student_count,
        message=data.message.strip() if data.message else None,
        status="new",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead
