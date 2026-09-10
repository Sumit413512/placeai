from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, require_institution_admin, require_recruiter
from app.models import (
    Announcement,
    Application,
    DriveStage,
    Notification,
    Offer,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.routers.enterprise import (
    DEFAULT_PIPELINE,
    _announcement_matches_student,
    _application_access,
    _org_for_user,
    _recruiter,
    _serialize_offer,
    _student,
)
from app.schemas import AnnouncementCreate, DriveStageCreate, OfferUpdate
from app.services import create_notification, record_audit
from app.storage import (
    delete_file,
    file_download_response,
    safe_upload_filename,
    save_file,
    validate_upload_signature,
)

settings = get_settings()
router = APIRouter(tags=["Production hardening v2"])
PLACED_OFFER_STATUSES = {"accepted", "joining_confirmed", "joined"}


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _announcement_active(row: Announcement, now: datetime | None = None) -> bool:
    point = now or _utc_naive_now()
    starts_at = _utc_naive(row.starts_at)
    expires_at = _utc_naive(row.expires_at)
    if starts_at is not None and starts_at > point:
        return False
    if expires_at is not None and expires_at <= point:
        return False
    return True


def _announcement_state(row: Announcement, now: datetime | None = None) -> str:
    point = now or _utc_naive_now()
    starts_at = _utc_naive(row.starts_at)
    expires_at = _utc_naive(row.expires_at)
    if expires_at is not None and expires_at <= point:
        return "expired"
    if starts_at is not None and starts_at > point:
        return "scheduled"
    return "active"


def _announcement_payload(row: Announcement, now: datetime | None = None) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "audience_type": row.audience_type,
        "audience_value": row.audience_value,
        "priority": row.priority,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "delivery_state": _announcement_state(row, now),
    }


def _ensure_announcement_notification(
    db: Session,
    row: Announcement,
    student: StudentProfile,
) -> bool:
    link = f"announcements:{row.id}"
    exists = db.query(Notification).filter(
        Notification.user_id == student.user_id,
        Notification.category == "announcement",
        Notification.link == link,
    ).first()
    if exists:
        return False
    create_notification(
        db,
        student.user_id,
        row.title,
        row.body[:500],
        organization_id=row.organization_id,
        category="announcement",
        priority=row.priority,
        link=link,
    )
    return True


@router.get("/enterprise/announcements")
def hardened_list_announcements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = _org_for_user(current_user, db)
    rows = db.query(Announcement).filter(
        Announcement.organization_id == org.id
    ).order_by(Announcement.created_at.desc()).all()
    now = _utc_naive_now()

    if current_user.role == UserRole.student:
        student = _student(current_user, db)
        rows = [
            row
            for row in rows
            if _announcement_active(row, now)
            and _announcement_matches_student(row, student, db)
        ]
        created = False
        for row in rows:
            created = _ensure_announcement_notification(db, row, student) or created
        if created:
            db.commit()
    return [_announcement_payload(row, now) for row in rows]


@router.post("/enterprise/announcements", status_code=status.HTTP_201_CREATED)
def hardened_create_announcement(
    data: AnnouncementCreate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org_for_user(current_user, db)
    starts_at = _utc_naive(data.starts_at)
    expires_at = _utc_naive(data.expires_at)
    if starts_at is not None and expires_at is not None and expires_at <= starts_at:
        raise HTTPException(status_code=422, detail="Announcement expiry must be after its start time")

    row = Announcement(
        organization_id=org.id,
        created_by_user_id=current_user.id,
        title=data.title,
        body=data.body,
        audience_type=data.audience_type,
        priority=data.priority,
        starts_at=starts_at,
        expires_at=expires_at,
    )
    row.audience_value = data.audience_value
    db.add(row)
    db.flush()

    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org.id).all()
    notified = 0
    if _announcement_active(row):
        for student in students:
            if _announcement_matches_student(row, student, db):
                notified += int(_ensure_announcement_notification(db, row, student))

    record_audit(
        db,
        current_user,
        "institution.announcement.created",
        organization_id=org.id,
        entity_type="announcement",
        entity_id=row.id,
        metadata={
            "audience": row.audience_type,
            "delivery_state": _announcement_state(row),
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "title": row.title,
        "audience_type": row.audience_type,
        "delivery_state": _announcement_state(row),
        "notified_students": notified,
    }


def _drive_for_institution(drive_id: str, current_user: User, db: Session) -> PlacementDrive:
    org = _org_for_user(current_user, db)
    drive = db.query(PlacementDrive).filter(
        PlacementDrive.id == drive_id,
        PlacementDrive.organization_id == org.id,
    ).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    return drive


def _pipeline_payload(drive_id: str, db: Session) -> list[dict]:
    stages = db.query(DriveStage).filter(
        DriveStage.drive_id == drive_id
    ).order_by(DriveStage.order_index.asc()).all()
    return [
        {
            "id": stage.id,
            "stage_key": stage.stage_key,
            "name": stage.name,
            "order_index": stage.order_index,
            "stage_type": stage.stage_type,
            "is_terminal": stage.is_terminal,
        }
        for stage in stages
    ]


@router.post("/enterprise/drives/{drive_id}/pipeline/default")
def hardened_install_default_pipeline(
    drive_id: str,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    drive = _drive_for_institution(drive_id, current_user, db)
    existing = db.query(DriveStage).filter(DriveStage.drive_id == drive.id).count()
    if not existing:
        for index, (key, name, stage_type) in enumerate(DEFAULT_PIPELINE):
            db.add(
                DriveStage(
                    drive_id=drive.id,
                    stage_key=key,
                    name=name,
                    order_index=index,
                    stage_type=stage_type,
                    is_terminal=(key == "joined"),
                )
            )
        record_audit(
            db,
            current_user,
            "institution.drive.pipeline_default_installed",
            organization_id=drive.organization_id,
            entity_type="placement_drive",
            entity_id=drive.id,
        )
        db.commit()
    return _pipeline_payload(drive.id, db)


@router.post("/enterprise/drives/{drive_id}/pipeline", status_code=status.HTTP_201_CREATED)
def hardened_add_pipeline_stage(
    drive_id: str,
    data: DriveStageCreate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    drive = _drive_for_institution(drive_id, current_user, db)
    key = (data.stage_key or data.name.lower().replace(" ", "-")).strip("-")
    if not key:
        raise HTTPException(status_code=422, detail="A valid pipeline stage key is required")
    duplicate = db.query(DriveStage).filter(
        DriveStage.drive_id == drive.id,
        DriveStage.stage_key == key,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Pipeline stage key already exists")
    order_index = (
        data.order_index
        if data.order_index is not None
        else db.query(DriveStage).filter(DriveStage.drive_id == drive.id).count()
    )
    stage = DriveStage(
        drive_id=drive.id,
        stage_key=key,
        name=data.name,
        order_index=order_index,
        stage_type=data.stage_type,
        is_terminal=data.is_terminal,
    )
    db.add(stage)
    db.flush()
    record_audit(
        db,
        current_user,
        "institution.drive.pipeline_stage_added",
        organization_id=drive.organization_id,
        entity_type="drive_stage",
        entity_id=stage.id,
        metadata={"stage_key": key, "drive_id": drive.id},
    )
    db.commit()
    db.refresh(stage)
    return {
        "id": stage.id,
        "stage_key": stage.stage_key,
        "name": stage.name,
        "order_index": stage.order_index,
        "stage_type": stage.stage_type,
        "is_terminal": stage.is_terminal,
    }


def _recalculate_student_placement_status(student_id: str, db: Session) -> str:
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if not student:
        return "unplaced"
    statuses = [
        offer.status
        for offer in db.query(Offer)
        .join(Application, Offer.application_id == Application.id)
        .filter(Application.student_id == student.id)
        .all()
    ]
    student.placement_status = (
        "placed" if any((value or "").lower() in PLACED_OFFER_STATUSES for value in statuses) else "unplaced"
    )
    return student.placement_status


@router.patch("/enterprise/offers/{offer_id}")
def hardened_update_offer(
    offer_id: str,
    data: OfferUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    application = db.query(Application).filter(Application.id == offer.application_id).first()
    if not application or not _application_access(current_user, application, db):
        raise HTTPException(status_code=403, detail="Not permitted")

    if current_user.role == UserRole.student:
        if data.status not in {"accepted", "declined"}:
            raise HTTPException(status_code=403, detail="Students may only accept or decline offers")
        payload = {"status": data.status}
    else:
        payload = data.model_dump(exclude_unset=True)

    for key, value in payload.items():
        setattr(offer, key, value)
    if application.student_id:
        _recalculate_student_placement_status(application.student_id, db)
    record_audit(
        db,
        current_user,
        "offer.updated",
        organization_id=application.student.organization_id if application.student else None,
        entity_type="offer",
        entity_id=offer.id,
        metadata={"fields": sorted(payload)},
    )
    db.commit()
    db.refresh(offer)
    return _serialize_offer(offer, db)


@router.post("/enterprise/company-verification/authorization-letter")
async def hardened_upload_authorization_letter(
    file: UploadFile = File(...),
    current_user: User = Depends(require_recruiter),
    db: Session = Depends(get_db),
):
    profile = _recruiter(current_user, db)
    extension = Path(file.filename or "letter.pdf").suffix.lower()
    if extension != ".pdf":
        raise HTTPException(status_code=400, detail="Authorization letter must be a PDF")
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Authorization letter must be 5 MB or smaller")
    validate_upload_signature(raw, ".pdf")

    previous = profile.authorization_letter_path
    path = settings.upload_dir.parent / "company-verification" / f"{profile.id}-{secrets.token_hex(8)}.pdf"
    replacement = save_file(
        db,
        category="company-verification",
        original_filename=safe_upload_filename(file.filename, "authorization-letter.pdf"),
        mime_type="application/pdf",
        data=raw,
        local_path=path,
    )
    profile.authorization_letter_path = replacement
    if previous and previous != replacement:
        delete_file(db, previous)
    db.commit()
    return {"uploaded": True, "filename": safe_upload_filename(file.filename, "authorization-letter.pdf")}


@router.post("/enterprise/offers/{offer_id}/letter")
async def hardened_upload_offer_letter(
    offer_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    application = db.query(Application).filter(Application.id == offer.application_id).first()
    if (
        not application
        or not _application_access(current_user, application, db)
        or current_user.role == UserRole.student
    ):
        raise HTTPException(status_code=403, detail="Not permitted")

    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Offer letter must be 8 MB or smaller")
    validate_upload_signature(raw, ".pdf")

    previous = offer.offer_letter_path
    path = settings.upload_dir.parent / "offer-letters" / f"{offer.id}-{secrets.token_hex(8)}.pdf"
    replacement = save_file(
        db,
        category="offer-letter",
        original_filename=safe_upload_filename(file.filename, "offer-letter.pdf"),
        mime_type="application/pdf",
        data=raw,
        local_path=path,
    )
    offer.offer_letter_path = replacement
    if previous and previous != replacement:
        delete_file(db, previous)
    db.commit()
    return {"uploaded": True, "filename": safe_upload_filename(file.filename, "offer-letter.pdf")}


@router.get("/enterprise/offers/{offer_id}/letter")
def hardened_download_offer_letter(
    offer_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    application = db.query(Application).filter(Application.id == offer.application_id).first()
    if not application or not _application_access(current_user, application, db):
        raise HTTPException(status_code=403, detail="Not permitted")
    if not offer.offer_letter_path:
        raise HTTPException(status_code=404, detail="Offer letter has not been uploaded")
    safe_company = "".join(
        char for char in (offer.company_name or "company") if char.isalnum() or char in {"-", "_"}
    )[:60] or "company"
    return file_download_response(
        db,
        offer.offer_letter_path,
        media_type="application/pdf",
        filename=f"{safe_company}-offer-letter.pdf",
    )
