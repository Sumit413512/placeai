from __future__ import annotations

import csv
import io
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, require_institution_admin, require_recruiter, require_student
from app.models import (
    Announcement,
    Application,
    ApprovalStatus,
    AttendanceRecord,
    AttendanceSession,
    CommunicationMessage,
    CommunicationThread,
    CustomFieldDefinition,
    CustomFieldValue,
    DriveStage,
    DriveStatus,
    IncidentReport,
    InstitutionPolicy,
    InterviewEvaluation,
    InterviewSchedule,
    Job,
    Notification,
    NotificationPreference,
    Offer,
    Organization,
    PlacementDrive,
    ProfileChangeRequest,
    RecruiterProfile,
    StudentDocument,
    StudentProfile,
    User,
    UserRole,
    utcnow,
)
from app.schemas import (
    AnnouncementCreate,
    AttendanceSessionCreate,
    CommunicationMessageCreate,
    CommunicationThreadCreate,
    CustomFieldCreate,
    CustomFieldValueUpdate,
    DriveStageCreate,
    IncidentReportCreate,
    IncidentStatusUpdate,
    InstitutionPolicyCreate,
    InterviewEvaluationCreate,
    InterviewScheduleCreate,
    InterviewScheduleUpdate,
    NotificationPreferenceUpdate,
    OfferCreate,
    OfferUpdate,
    ProfileChangeReview,
)
from app.services import (
    company_trust_assessment,
    create_notification,
    evaluate_drive_eligibility,
    institution_analytics_v2,
    institution_attention_centre,
    placement_readiness,
    record_audit,
)
from app.storage import delete_file, file_download_response, save_file, safe_upload_filename, validate_upload_signature

settings = get_settings()
router = APIRouter(prefix="/enterprise", tags=["Enterprise Placement Operations"])


PLACED_OFFER_STATUSES = {"accepted", "joining_confirmed", "joined"}
VALID_OFFER_STATUSES = {"issued", "accepted", "declined", "withdrawn", "joining_confirmed", "joined"}
STUDENT_OFFER_DECISIONS = {"accepted", "declined"}
OPERATOR_OFFER_STATUSES = VALID_OFFER_STATUSES - STUDENT_OFFER_DECISIONS
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


def _org_for_user(user: User, db: Session) -> Organization:
    if not user.organization_id:
        if user.role == UserRole.recruiter:
            rp = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).first()
            if rp and rp.provisioned_by_organization_id:
                org = db.query(Organization).filter(Organization.id == rp.provisioned_by_organization_id).first()
                if org:
                    return org
        raise HTTPException(status_code=403, detail="Account is not linked to an institution")
    org = db.query(Organization).filter(Organization.id == user.organization_id, Organization.is_active.is_(True)).first()
    if not org:
        raise HTTPException(status_code=403, detail="Institution is inactive or unavailable")
    return org


def _student(user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _recruiter(user: User, db: Session) -> RecruiterProfile:
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    return profile


def _application_access(user: User, application: Application, db: Session) -> bool:
    if user.role == UserRole.student:
        s = _student(user, db)
        return application.student_id == s.id
    if user.role == UserRole.recruiter:
        r = _recruiter(user, db)
        return bool(application.job and application.job.recruiter_id == r.id)
    if user.role == UserRole.institution_admin:
        return bool(application.student and application.student.organization_id == user.organization_id)
    return user.role == UserRole.platform_admin


def _thread_for_user(thread_id: str, user: User, db: Session) -> CommunicationThread:
    org = _org_for_user(user, db)
    thread = db.query(CommunicationThread).filter(
        CommunicationThread.id == thread_id,
        CommunicationThread.organization_id == org.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if user.role == UserRole.recruiter and thread.recruiter_profile_id != _recruiter(user, db).id:
        raise HTTPException(status_code=404, detail="Thread not found")
    if user.role not in {UserRole.recruiter, UserRole.institution_admin, UserRole.platform_admin}:
        raise HTTPException(status_code=403, detail="Not permitted")
    return thread


def _serialize_notification(n: Notification) -> dict:
    return {
        "id": n.id, "title": n.title, "message": n.message, "category": n.category,
        "priority": n.priority, "link": n.link, "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def _serialize_interview(iv: InterviewSchedule, db: Session) -> dict:
    app = db.query(Application).filter(Application.id == iv.application_id).first()
    student = app.student if app else None
    job = app.job if app else None
    return {
        "id": iv.id, "application_id": iv.application_id, "drive_id": iv.drive_id,
        "round_name": iv.round_name, "scheduled_at": iv.scheduled_at.isoformat() if iv.scheduled_at else None,
        "mode": iv.mode, "venue": iv.venue, "meeting_url": iv.meeting_url,
        "interviewer": iv.interviewer, "student_slot": iv.student_slot, "instructions": iv.instructions,
        "status": iv.status, "attendance_status": iv.attendance_status, "result": iv.result,
        "student_name": student.full_name if student else None,
        "job_title": job.title if job else None,
        "company_name": job.recruiter.company_name if job and job.recruiter else None,
    }


def _serialize_offer(o: Offer, db: Session) -> dict:
    app = db.query(Application).filter(Application.id == o.application_id).first()
    return {
        "id": o.id, "application_id": o.application_id, "company_name": o.company_name, "role": o.role,
        "student_name": app.student.full_name if app and app.student else None,
        "student_id": app.student_id if app else None,
        "ctc_lpa": o.ctc_lpa, "fixed_pay_lpa": o.fixed_pay_lpa, "variable_pay_lpa": o.variable_pay_lpa,
        "location": o.location, "joining_date": o.joining_date.isoformat() if o.joining_date else None,
        "status": o.status, "bond_terms": o.bond_terms, "internship_stipend": o.internship_stipend,
        "ppo_status": o.ppo_status, "has_offer_letter": bool(o.offer_letter_path),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# -----------------------------------------------------------------------------
# Priority 1: Company Verification Centre
# -----------------------------------------------------------------------------
@router.get("/company-verification")
def company_verification(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _recruiter(current_user, db)
    assessment = company_trust_assessment(profile, db)
    profile.company_verification_status = assessment.verification_status
    profile.company_verification_confidence = assessment.confidence
    db.commit()
    return {
        "company": {
            "id": profile.id,
            "company_name": profile.company_name,
            "cin": profile.cin,
            "gstin": profile.gstin,
            "official_website": profile.company_website,
            "official_email_domain": profile.official_email_domain,
            "linkedin_url": profile.linkedin_url,
            "company_address": profile.company_address,
            "recruiter_identity": profile.full_name,
            "recruiter_designation": profile.designation,
            "institution_verified": profile.is_verified,
            "authorization_letter_on_file": bool(profile.authorization_letter_path),
            "past_college_relationships": profile.past_college_relationships,
            "previous_successful_placements": profile.previous_successful_placements,
            "job_information_consistency": profile.job_consistency_score,
            "suspicious_domain": profile.suspicious_domain,
        },
        "assessment": assessment.model_dump(),
    }


@router.get("/institution/company-verification/{recruiter_id}")
def institution_company_verification(recruiter_id: str, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.id == recruiter_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    linked = profile.provisioned_by_organization_id == org.id or db.query(Job).filter(Job.recruiter_id == profile.id, Job.target_organization_id == org.id).first()
    if not linked:
        raise HTTPException(status_code=404, detail="Recruiter is not linked to this institution")
    assessment = company_trust_assessment(profile, db)
    return {"company": {"id": profile.id, "company_name": profile.company_name, "cin": profile.cin, "gstin": profile.gstin, "company_address": profile.company_address}, "assessment": assessment.model_dump()}


@router.post("/company-verification/authorization-letter")
async def upload_authorization_letter(
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

# Generic drive discovery for pipeline/calendar UI.
@router.get("/drives")
def enterprise_drives(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.student:
        s = _student(current_user, db)
        rows = db.query(PlacementDrive).filter(PlacementDrive.organization_id == s.organization_id).order_by(PlacementDrive.created_at.desc()).all()
    elif current_user.role == UserRole.institution_admin:
        rows = db.query(PlacementDrive).filter(PlacementDrive.organization_id == current_user.organization_id).order_by(PlacementDrive.created_at.desc()).all()
    elif current_user.role == UserRole.recruiter:
        r = _recruiter(current_user, db)
        rows = db.query(PlacementDrive).join(Job, PlacementDrive.job_id == Job.id).filter(Job.recruiter_id == r.id).order_by(PlacementDrive.created_at.desc()).all()
    else:
        rows = db.query(PlacementDrive).order_by(PlacementDrive.created_at.desc()).limit(200).all()
    return [{"id":d.id,"title":d.title,"job_id":d.job_id,"job_title":d.job.title if d.job else None,"company_name":d.job.recruiter.company_name if d.job and d.job.recruiter else None,"status":d.status.value if hasattr(d.status,'value') else str(d.status),"event_date":d.event_date.isoformat() if d.event_date else None,"registration_deadline":d.registration_deadline.isoformat() if d.registration_deadline else None} for d in rows]


# -----------------------------------------------------------------------------
# Priority 2: Advanced placement pipeline
# -----------------------------------------------------------------------------
DEFAULT_PIPELINE = [
    ("registration", "Registration", "registration"),
    ("eligibility-screening", "Eligibility Screening", "screening"),
    ("online-assessment", "Online Assessment", "assessment"),
    ("technical-round-1", "Technical Round 1", "interview"),
    ("technical-round-2", "Technical Round 2", "interview"),
    ("hr-interview", "HR Interview", "interview"),
    ("offer", "Offer", "offer"),
    ("joined", "Joined", "terminal"),
]


@router.get("/drives/{drive_id}/pipeline")
def get_pipeline(drive_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    if current_user.role == UserRole.student:
        if _student(current_user, db).organization_id != drive.organization_id:
            raise HTTPException(status_code=404, detail="Drive not found")
    elif current_user.role == UserRole.institution_admin and current_user.organization_id != drive.organization_id:
        raise HTTPException(status_code=404, detail="Drive not found")
    elif current_user.role == UserRole.recruiter:
        if not drive.job or drive.job.recruiter_id != _recruiter(current_user, db).id:
            raise HTTPException(status_code=404, detail="Drive not found")
    stages = db.query(DriveStage).filter(DriveStage.drive_id == drive.id).order_by(DriveStage.order_index.asc()).all()
    return [{"id": s.id, "stage_key": s.stage_key, "name": s.name, "order_index": s.order_index, "stage_type": s.stage_type, "is_terminal": s.is_terminal} for s in stages]


@router.post("/drives/{drive_id}/pipeline/default")
def install_default_pipeline(
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

@router.post("/drives/{drive_id}/pipeline")
def add_pipeline_stage(
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

@router.patch("/applications/{application_id}/pipeline/{stage_key}")
def move_pipeline_stage(application_id: str, stage_key: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app or not _application_access(current_user, app, db) or current_user.role == UserRole.student:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.drive_id:
        stage = db.query(DriveStage).filter(DriveStage.drive_id == app.drive_id, DriveStage.stage_key == stage_key).first()
        if not stage:
            raise HTTPException(status_code=400, detail="Stage does not exist in this drive pipeline")
    app.pipeline_stage_key = stage_key
    student_user_id = app.student.user_id if app.student else None
    if student_user_id:
        create_notification(db, student_user_id, "Application stage updated", f"Your {app.job.title} application moved to {stage_key.replace('-', ' ').title()}.", organization_id=app.student.organization_id, category="application", link="applications")
    db.commit()
    return {"application_id": app.id, "pipeline_stage_key": app.pipeline_stage_key}


# -----------------------------------------------------------------------------
# Priority 3 + 12: Interview scheduling and human evaluation
# -----------------------------------------------------------------------------
@router.get("/interviews")
def list_interviews(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(InterviewSchedule)
    rows = q.order_by(InterviewSchedule.scheduled_at.asc()).all()
    visible = []
    for iv in rows:
        app = db.query(Application).filter(Application.id == iv.application_id).first()
        if app and _application_access(current_user, app, db):
            visible.append(_serialize_interview(iv, db))
    return visible


@router.post("/interviews", status_code=status.HTTP_201_CREATED)
def create_interview(data: InterviewScheduleCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in {UserRole.recruiter, UserRole.institution_admin, UserRole.platform_admin}:
        raise HTTPException(status_code=403, detail="Only placement teams and recruiters can schedule interviews")
    app = db.query(Application).filter(Application.id == data.application_id).first()
    if not app or not _application_access(current_user, app, db):
        raise HTTPException(status_code=404, detail="Application not found")
    if data.drive_id:
        drive = db.query(PlacementDrive).filter(PlacementDrive.id == data.drive_id).first()
        if not drive or drive.job_id != app.job_id:
            raise HTTPException(status_code=400, detail="Interview drive does not match the application job")
        if app.drive_id and drive.id != app.drive_id:
            raise HTTPException(status_code=400, detail="Interview drive does not match the application drive")
        if app.student and drive.organization_id != app.student.organization_id:
            raise HTTPException(status_code=400, detail="Interview drive does not belong to the student's institution")
    iv = InterviewSchedule(**data.model_dump(), created_by_user_id=current_user.id)
    db.add(iv)
    if app.student:
        create_notification(db, app.student.user_id, "Interview scheduled", f"{data.round_name} for {app.job.title} is scheduled for {data.scheduled_at.strftime('%d %b %Y, %I:%M %p')}.", organization_id=app.student.organization_id, category="interview", priority="high", link="interviews")
    record_audit(db, current_user, "interview.scheduled", organization_id=app.student.organization_id if app.student else None, entity_type="interview", entity_id=iv.id, metadata={"round": data.round_name, "application_id": app.id})
    db.commit(); db.refresh(iv)
    return _serialize_interview(iv, db)


@router.patch("/interviews/{interview_id}")
def update_interview(interview_id: str, data: InterviewScheduleUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    iv = db.query(InterviewSchedule).filter(InterviewSchedule.id == interview_id).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    app = db.query(Application).filter(Application.id == iv.application_id).first()
    if not app or not _application_access(current_user, app, db) or current_user.role == UserRole.student:
        raise HTTPException(status_code=403, detail="Not permitted")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(iv, k, v)
    if app.student:
        create_notification(db, app.student.user_id, "Interview updated", f"Your {iv.round_name} interview details changed. Review the latest schedule.", organization_id=app.student.organization_id, category="interview", priority="high", link="interviews")
    db.commit(); db.refresh(iv)
    return _serialize_interview(iv, db)


@router.put("/interviews/{interview_id}/evaluation")
def save_interview_evaluation(interview_id: str, data: InterviewEvaluationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in {UserRole.recruiter, UserRole.institution_admin, UserRole.platform_admin}:
        raise HTTPException(status_code=403, detail="Not permitted")
    iv = db.query(InterviewSchedule).filter(InterviewSchedule.id == interview_id).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    app = db.query(Application).filter(Application.id == iv.application_id).first()
    if not app or not _application_access(current_user, app, db):
        raise HTTPException(status_code=403, detail="Not permitted")
    ev = db.query(InterviewEvaluation).filter(InterviewEvaluation.interview_id == iv.id).first() or InterviewEvaluation(interview_id=iv.id, evaluator_user_id=current_user.id)
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(ev, k, v)
    db.add(ev); db.commit(); db.refresh(ev)
    return {"id": ev.id, "interview_id": ev.interview_id, "technical_knowledge": ev.technical_knowledge, "communication": ev.communication, "problem_solving": ev.problem_solving, "role_fit": ev.role_fit, "recommendation": ev.recommendation, "notes": ev.notes, "human_reviewed": True}


# -----------------------------------------------------------------------------
# Priority 4: Database-backed notification centre
# -----------------------------------------------------------------------------
@router.get("/notifications")
def list_notifications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return {"unread": sum(1 for n in rows if not n.is_read), "items": [_serialize_notification(n) for n in rows]}


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if not n: raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True; db.commit(); return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_notifications_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read.is_(False)).update({Notification.is_read: True}, synchronize_session=False)
    db.commit(); return {"ok": True}


@router.get("/notification-preferences")
def get_notification_preferences(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(NotificationPreference).filter(NotificationPreference.user_id == current_user.id).first()
    if not p:
        p = NotificationPreference(user_id=current_user.id); db.add(p); db.commit(); db.refresh(p)
    return {"in_app": p.in_app, "email": p.email, "whatsapp": p.whatsapp, "sms": p.sms, "high_priority_only_external": p.high_priority_only_external}


@router.put("/notification-preferences")
def update_notification_preferences(data: NotificationPreferenceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(NotificationPreference).filter(NotificationPreference.user_id == current_user.id).first() or NotificationPreference(user_id=current_user.id)
    for k,v in data.model_dump().items(): setattr(p,k,v)
    db.add(p); db.commit(); return data.model_dump()


# -----------------------------------------------------------------------------
# Priority 5: Placement Readiness
# -----------------------------------------------------------------------------
@router.get("/readiness")
def student_readiness(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    return placement_readiness(_student(current_user, db), db)


# -----------------------------------------------------------------------------
# Priority 7: Advanced eligibility
# -----------------------------------------------------------------------------
@router.get("/drives/{drive_id}/eligibility")
def advanced_eligibility(drive_id: str, current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    s = _student(current_user, db)
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id, PlacementDrive.organization_id == s.organization_id).first()
    if not drive: raise HTTPException(status_code=404, detail="Drive not found")
    return evaluate_drive_eligibility(s, drive, db)


# -----------------------------------------------------------------------------
# Priority 8: Placement policy engine
# -----------------------------------------------------------------------------
@router.get("/policies")
def list_policies(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    rows = db.query(InstitutionPolicy).filter(InstitutionPolicy.organization_id == org.id).order_by(InstitutionPolicy.name.asc()).all()
    return [{"id": p.id, "policy_key": p.policy_key, "name": p.name, "description": p.description, "rules": p.rules, "is_active": p.is_active} for p in rows]


@router.post("/policies", status_code=status.HTTP_201_CREATED)
def create_policy(data: InstitutionPolicyCreate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    p = InstitutionPolicy(organization_id=org.id, policy_key=data.policy_key, name=data.name, description=data.description, is_active=data.is_active); p.rules = data.rules
    db.add(p); record_audit(db, current_user, "institution.policy.created", organization_id=org.id, entity_type="institution_policy", entity_id=p.id, metadata={"policy_key": p.policy_key}); db.commit(); db.refresh(p)
    return {"id": p.id, "policy_key": p.policy_key, "name": p.name, "description": p.description, "rules": p.rules, "is_active": p.is_active}


# -----------------------------------------------------------------------------
# Priority 9: Offer management
# -----------------------------------------------------------------------------
@router.get("/offers")
def list_offers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Offer).order_by(Offer.created_at.desc()).all()
    result = []
    for o in rows:
        app = db.query(Application).filter(Application.id == o.application_id).first()
        if app and _application_access(current_user, app, db): result.append(_serialize_offer(o, db))
    return result


@router.post("/offers", status_code=status.HTTP_201_CREATED)
def create_offer(data: OfferCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in {UserRole.recruiter, UserRole.institution_admin, UserRole.platform_admin}: raise HTTPException(status_code=403, detail="Not permitted")
    app = db.query(Application).filter(Application.id == data.application_id).first()
    if not app or not _application_access(current_user, app, db): raise HTTPException(status_code=404, detail="Application not found")
    existing = db.query(Offer).filter(Offer.application_id == app.id).first()
    if existing: raise HTTPException(status_code=409, detail="An offer already exists for this application")
    company = app.job.recruiter.company_name if app.job and app.job.recruiter else "Company"
    offer = Offer(application_id=app.id, company_name=company or "Company", role=app.job.title if app.job else "Role", **data.model_dump(exclude={"application_id"}))
    db.add(offer)
    if app.student:
        app.student.offers_count = (app.student.offers_count or 0) + 1
        create_notification(db, app.student.user_id, "Offer issued", f"{company} issued an offer for {offer.role}.", organization_id=app.student.organization_id, category="offer", priority="high", link="offers")
    db.commit(); db.refresh(offer)
    return _serialize_offer(offer, db)


@router.patch("/offers/{offer_id}")
def update_offer(
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

    normalized_status = None
    if data.status is not None:
        normalized_status = data.status.strip().lower()
        if not normalized_status or normalized_status not in VALID_OFFER_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported offer status")

    if current_user.role == UserRole.student:
        if normalized_status not in STUDENT_OFFER_DECISIONS:
            raise HTTPException(status_code=403, detail="Students may only accept or decline offers")
        payload = {"status": normalized_status}
    else:
        if normalized_status in STUDENT_OFFER_DECISIONS:
            raise HTTPException(status_code=403, detail="Only the student may accept or decline an offer")
        payload = data.model_dump(exclude_unset=True)
        if "status" in payload:
            if normalized_status not in OPERATOR_OFFER_STATUSES:
                raise HTTPException(status_code=422, detail="Unsupported offer status")
            payload["status"] = normalized_status

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

@router.post("/offers/{offer_id}/letter")
async def upload_offer_letter(
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

@router.get("/offers/{offer_id}/letter")
def download_offer_letter(
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

# -----------------------------------------------------------------------------
# Priority 10: Student document vault
# -----------------------------------------------------------------------------
@router.get("/documents")
def list_documents(current_user: User = Depends(get_current_user), student_id: str | None = None, db: Session = Depends(get_db)):
    if current_user.role == UserRole.student:
        s = _student(current_user, db)
    elif current_user.role == UserRole.institution_admin:
        if not student_id: raise HTTPException(status_code=400, detail="student_id is required")
        s = db.query(StudentProfile).filter(StudentProfile.id == student_id, StudentProfile.organization_id == current_user.organization_id).first()
        if not s: raise HTTPException(status_code=404, detail="Student not found")
    else:
        raise HTTPException(status_code=403, detail="Document vault is limited to students and institution teams")
    rows = db.query(StudentDocument).filter(StudentDocument.student_id == s.id).order_by(StudentDocument.uploaded_at.desc()).all()
    return [{"id": d.id, "document_type": d.document_type, "filename": d.original_filename, "visibility": d.visibility, "is_verified": d.is_verified, "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None} for d in rows]


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(document_type: str, visibility: str = "institution_only", file: UploadFile = File(...), current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    s = _student(current_user, db)
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024: raise HTTPException(status_code=413, detail="Document must be 10 MB or smaller")
    safe_ext = Path(file.filename or "document").suffix.lower()
    if safe_ext not in {".pdf", ".png", ".jpg", ".jpeg"}: raise HTTPException(status_code=400, detail="Supported document types: PDF, PNG, JPG")
    mime_type = validate_upload_signature(raw, safe_ext)
    path = settings.upload_dir.parent / "student-documents" / s.id / f"{secrets.token_hex(10)}{safe_ext}"
    original_name = safe_upload_filename(file.filename, f"document{safe_ext}")
    reference = save_file(
        db, category="student-document", original_filename=original_name, mime_type=mime_type, data=raw, local_path=path
    )
    d = StudentDocument(student_id=s.id, document_type=document_type, original_filename=original_name, filepath=reference, visibility=visibility)
    db.add(d); db.commit(); db.refresh(d)
    return {"id": d.id, "document_type": d.document_type, "filename": d.original_filename, "visibility": d.visibility, "is_verified": d.is_verified}


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = db.query(StudentDocument).filter(StudentDocument.id == document_id).first()
    if not d: raise HTTPException(status_code=404, detail="Document not found")
    s = db.query(StudentProfile).filter(StudentProfile.id == d.student_id).first()
    if current_user.role == UserRole.student and (not s or s.user_id != current_user.id): raise HTTPException(status_code=404, detail="Document not found")
    if current_user.role == UserRole.institution_admin and (not s or s.organization_id != current_user.organization_id): raise HTTPException(status_code=404, detail="Document not found")
    if current_user.role not in {UserRole.student, UserRole.institution_admin, UserRole.platform_admin}: raise HTTPException(status_code=403, detail="Not permitted")
    return file_download_response(db, d.filepath, filename=d.original_filename)


# -----------------------------------------------------------------------------
# Priority 11: QR attendance
# -----------------------------------------------------------------------------
@router.get("/attendance/sessions")
def list_attendance_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    rows = db.query(AttendanceSession).filter(AttendanceSession.organization_id == org.id).order_by(AttendanceSession.created_at.desc()).all()
    return [{"id": s.id, "title": s.title, "session_type": s.session_type, "drive_id": s.drive_id, "starts_at": s.starts_at.isoformat() if s.starts_at else None, "closes_at": s.closes_at.isoformat() if s.closes_at else None, "is_active": s.is_active, "checkins": db.query(AttendanceRecord).filter(AttendanceRecord.session_id == s.id).count()} for s in rows]


@router.post("/attendance/sessions", status_code=status.HTTP_201_CREATED)
def create_attendance_session(data: AttendanceSessionCreate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    if data.drive_id:
        drive = db.query(PlacementDrive).filter(PlacementDrive.id == data.drive_id, PlacementDrive.organization_id == org.id).first()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found for this institution")
    if data.starts_at and data.closes_at and data.closes_at <= data.starts_at:
        raise HTTPException(status_code=400, detail="Attendance close time must be after the start time")
    s = AttendanceSession(organization_id=org.id, drive_id=data.drive_id, title=data.title, session_type=data.session_type, starts_at=data.starts_at, closes_at=data.closes_at, token=secrets.token_urlsafe(24), created_by_user_id=current_user.id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "title": s.title, "token": s.token, "checkin_url": f"/enterprise/attendance/check-in?token={s.token}"}


@router.get("/attendance/sessions/{session_id}/qr")
def attendance_qr(session_id: str, request: Request, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db)
    s = db.query(AttendanceSession).filter(AttendanceSession.id == session_id, AttendanceSession.organization_id == org.id).first()
    if not s: raise HTTPException(status_code=404, detail="Attendance session not found")
    try:
        import qrcode
        # In local/LAN testing, BASE_URL commonly remains localhost, which creates a QR
        # that phones cannot reach. Prefer the host that actually requested the QR in
        # development; retain an explicitly configured public BASE_URL in deployment.
        configured = (settings.base_url or "").rstrip("/")
        configured_is_local = configured.startswith("http://localhost") or configured.startswith("http://127.0.0.1")
        request_base = str(request.base_url).rstrip("/")
        public_base = request_base if configured_is_local else (configured or request_base)
        image = qrcode.make(f"{public_base}/?attendance_token={s.token}")
        buf = io.BytesIO(); image.save(buf, format="PNG"); buf.seek(0)
        return StreamingResponse(buf, media_type="image/png", headers={"Cache-Control": "no-store"})
    except Exception as exc:
        raise HTTPException(status_code=503, detail="QR rendering dependency unavailable") from exc


@router.post("/attendance/check-in")
def attendance_checkin(token: str, current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    s = _student(current_user, db)
    session = db.query(AttendanceSession).filter(AttendanceSession.token == token, AttendanceSession.is_active.is_(True), AttendanceSession.organization_id == s.organization_id).first()
    if not session: raise HTTPException(status_code=404, detail="Attendance session not found or inactive")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if session.starts_at and now < session.starts_at:
        raise HTTPException(status_code=425, detail="Attendance check-in has not opened yet")
    if session.closes_at and now > session.closes_at: raise HTTPException(status_code=410, detail="Attendance check-in has closed")
    record = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == s.id).first()
    if not record:
        record = AttendanceRecord(session_id=session.id, student_id=s.id); db.add(record); db.commit(); db.refresh(record)
    return {"checked_in": True, "session": session.title, "checked_in_at": record.checked_in_at.isoformat()}


# -----------------------------------------------------------------------------
# Priority 13: Attention centre
# -----------------------------------------------------------------------------
@router.get("/attention-centre")
def attention_centre(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db); return institution_attention_centre(org.id, db)


# -----------------------------------------------------------------------------
# Priority 14: Analytics 2.0
# -----------------------------------------------------------------------------
@router.get("/analytics/institution")
def analytics_institution(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db); return institution_analytics_v2(org.id, db)


@router.get("/analytics/recruiter")
def analytics_recruiter(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    r = _recruiter(current_user, db)
    apps = [a for j in r.jobs for a in j.applications]
    stage_counts: dict[str, int] = {}
    skill_counts: dict[str, int] = {}
    campus_counts: dict[str, dict[str, int]] = {}
    for a in apps:
        key = a.pipeline_stage_key or (a.status.value if hasattr(a.status, "value") else str(a.status))
        stage_counts[key] = stage_counts.get(key, 0) + 1
        if a.student:
            for skill in a.student.skills:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
            org = db.query(Organization).filter(Organization.id == a.student.organization_id).first() if a.student.organization_id else None
            campus = org.name if org else "Independent / public"
            bucket = campus_counts.setdefault(campus, {"applications": 0, "interviews": 0, "offers": 0})
            bucket["applications"] += 1
            status_value = a.status.value if hasattr(a.status, "value") else str(a.status)
            if status_value == "interview" or (a.pipeline_stage_key or "").startswith(("technical-", "hr-")):
                bucket["interviews"] += 1
    app_ids = [a.id for a in apps]
    interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(app_ids)).all() if app_ids else []
    offers = db.query(Offer).filter(Offer.application_id.in_(app_ids)).all() if app_ids else []
    offer_app_ids = {o.application_id for o in offers}
    for a in apps:
        if a.id in offer_app_ids and a.student:
            org = db.query(Organization).filter(Organization.id == a.student.organization_id).first() if a.student.organization_id else None
            campus = org.name if org else "Independent / public"
            campus_counts.setdefault(campus, {"applications": 0, "interviews": 0, "offers": 0})["offers"] += 1
    campus_comparison = []
    for campus, values in campus_counts.items():
        total = values["applications"]
        campus_comparison.append({
            "campus": campus,
            **values,
            "interview_conversion": round(values["interviews"] / total * 100, 1) if total else 0,
            "offer_conversion": round(values["offers"] / total * 100, 1) if total else 0,
        })
    campus_comparison.sort(key=lambda x: x["applications"], reverse=True)
    skill_availability = [{"skill": k, "candidates": v, "coverage": round(v / len(apps) * 100, 1) if apps else 0} for k, v in sorted(skill_counts.items(), key=lambda x: (-x[1], x[0].lower()))[:15]]
    return {
        "applications": len(apps),
        "qualified_candidates": sum(1 for a in apps if (a.ai_match_score or 0) >= 70),
        "pipeline": stage_counts,
        "interviews": len(interviews),
        "offers": len(offers),
        "interview_conversion": round(len(interviews)/len(apps)*100,1) if apps else 0,
        "offer_conversion": round(len(offers)/len(apps)*100,1) if apps else 0,
        "skill_availability": skill_availability,
        "campus_comparison": campus_comparison,
    }


# -----------------------------------------------------------------------------
# Priority 16: Role-aware command search
# -----------------------------------------------------------------------------
@router.get("/search")
def workspace_search(q: str = Query(min_length=1, max_length=120), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = q.strip()
    term = f"%{query}%"
    lowered = query.lower()
    results = []

    def job_matches(j: Job) -> bool:
        values = [
            j.title, j.description, j.location, j.job_type, j.salary_range, j.experience_required,
            j.recruiter.company_name if j.recruiter else "", *(j.required_skills or []), *(j.preferred_roles or []),
        ]
        return lowered in " ".join(str(v) for v in values if v).lower()

    if current_user.role in {UserRole.institution_admin, UserRole.platform_admin}:
        org_id = current_user.organization_id
        student_q = db.query(StudentProfile).filter(or_(StudentProfile.full_name.ilike(term), StudentProfile.branch.ilike(term), StudentProfile.degree.ilike(term)))
        if org_id:
            student_q = student_q.filter(StudentProfile.organization_id == org_id)
        for student in student_q.limit(8):
            results.append({"type":"student","id":student.id,"title":student.full_name or "Student","subtitle":f"{student.branch or ''} · {student.graduation_year or ''}","view":"students"})

        job_q = db.query(Job)
        if org_id:
            job_q = job_q.filter(or_(Job.target_organization_id == org_id, Job.visibility == "public"))
        for job in (j for j in job_q.order_by(Job.created_at.desc()).all() if job_matches(j)):
            results.append({"type":"job","id":job.id,"title":job.title,"subtitle":job.recruiter.company_name if job.recruiter else "Company","view":"jobs"})
            if len([x for x in results if x["type"] == "job"]) >= 8:
                break
    elif current_user.role == UserRole.recruiter:
        recruiter = _recruiter(current_user, db)
        matched_jobs = [job for job in recruiter.jobs if job_matches(job)]
        for job in sorted(matched_jobs, key=lambda x: x.created_at, reverse=True)[:8]:
            results.append({"type":"job","id":job.id,"title":job.title,"subtitle":job.location or "","view":"jobs"})
        ids = {a.student_id for job in recruiter.jobs for a in job.applications}
        if ids:
            candidates = db.query(StudentProfile).filter(StudentProfile.id.in_(ids)).all()
            candidates = [student for student in candidates if lowered in " ".join([student.full_name or "", student.branch or "", student.degree or "", " ".join(student.skills or [])]).lower()]
            for student in candidates[:8]:
                results.append({"type":"candidate","id":student.id,"title":student.full_name or "Candidate","subtitle":student.branch or "","view":"candidates"})
    else:
        student = _student(current_user, db)
        campus_job_ids = set()
        if student.organization_id:
            campus_job_ids = {
                drive.job_id for drive in db.query(PlacementDrive).filter(
                    PlacementDrive.organization_id == student.organization_id,
                    PlacementDrive.status.in_([DriveStatus.open, DriveStatus.draft]),
                ).all()
            }
        jobs = db.query(Job).filter(Job.is_active.is_(True), Job.approval_status == ApprovalStatus.approved).order_by(Job.created_at.desc()).all()
        visible = [job for job in jobs if job.visibility == "public" or job.id in campus_job_ids]
        for job in (j for j in visible if job_matches(j)):
            results.append({"type":"opportunity","id":job.id,"title":job.title,"subtitle":f"{job.recruiter.company_name if job.recruiter else 'Company'} · {job.location or 'Flexible location'}","view":"opportunities"})
            if len(results) >= 10:
                break
    return results[:20]


# -----------------------------------------------------------------------------
# Priority 17: Announcements
# -----------------------------------------------------------------------------
def _announcement_matches_student(a: Announcement, s: StudentProfile, db: Session) -> bool:
    v = a.audience_value
    if a.audience_type == "all_students": return True
    if a.audience_type == "branch": return (s.branch or "").lower() in {str(x).lower() for x in v.get("branches", [])}
    if a.audience_type == "batch": return s.graduation_year in v.get("graduation_years", [])
    if a.audience_type == "specific_students": return s.id in v.get("student_ids", [])
    if a.audience_type == "eligible_students":
        drive_id = v.get("drive_id")
        drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id, PlacementDrive.organization_id == s.organization_id).first() if drive_id else None
        return bool(drive and evaluate_drive_eligibility(s, drive, db)["eligible"])
    if a.audience_type == "drive_participants":
        drive_id = v.get("drive_id")
        return bool(drive_id and db.query(Application).filter(Application.student_id == s.id, Application.drive_id == drive_id).first())
    return False


@router.get("/announcements")
def list_announcements(
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

@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def create_announcement(
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

# -----------------------------------------------------------------------------
# Priority 18: Recruiter communication hub
# -----------------------------------------------------------------------------
@router.get("/communications")
def list_threads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org_for_user(current_user, db); q = db.query(CommunicationThread).filter(CommunicationThread.organization_id == org.id)
    if current_user.role == UserRole.recruiter: q = q.filter(CommunicationThread.recruiter_profile_id == _recruiter(current_user, db).id)
    rows = q.order_by(CommunicationThread.created_at.desc()).all()
    return [{"id":t.id,"subject":t.subject,"status":t.status,"drive_id":t.drive_id,"recruiter_profile_id":t.recruiter_profile_id,"message_count":db.query(CommunicationMessage).filter(CommunicationMessage.thread_id==t.id).count(),"created_at":t.created_at.isoformat()} for t in rows]


@router.post("/communications", status_code=status.HTTP_201_CREATED)
def create_thread(data: CommunicationThreadCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in {UserRole.institution_admin,UserRole.recruiter}: raise HTTPException(status_code=403,detail="Not permitted")
    org = _org_for_user(current_user, db)
    recruiter_id = data.recruiter_profile_id
    if current_user.role == UserRole.recruiter:
        recruiter_id = _recruiter(current_user, db).id
    if recruiter_id:
        recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.id == recruiter_id).first()
        linked = bool(recruiter and (
            recruiter.provisioned_by_organization_id == org.id or
            db.query(Job).filter(Job.recruiter_id == recruiter_id, Job.target_organization_id == org.id).first()
        ))
        if not linked:
            raise HTTPException(status_code=404, detail="Recruiter is not linked to this institution")
    if data.drive_id:
        drive = db.query(PlacementDrive).filter(PlacementDrive.id == data.drive_id, PlacementDrive.organization_id == org.id).first()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found for this institution")
        if recruiter_id and drive.job and drive.job.recruiter_id != recruiter_id:
            raise HTTPException(status_code=400, detail="Drive and recruiter do not match")
    t=CommunicationThread(organization_id=org.id,recruiter_profile_id=recruiter_id,drive_id=data.drive_id,subject=data.subject,created_by_user_id=current_user.id);db.add(t);db.commit();db.refresh(t);return {"id":t.id,"subject":t.subject,"status":t.status}


@router.get("/communications/{thread_id}/messages")
def thread_messages(thread_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _thread_for_user(thread_id, current_user, db)
    rows = db.query(CommunicationMessage).filter(CommunicationMessage.thread_id == t.id).order_by(CommunicationMessage.created_at.asc()).all()
    users = {u.id: u.email for u in db.query(User).filter(User.id.in_([m.sender_user_id for m in rows])).all()} if rows else {}
    return [{
        "id": m.id,
        "sender_user_id": m.sender_user_id,
        "sender_email": users.get(m.sender_user_id, "System"),
        "message": m.message,
        "has_attachment": bool(m.attachment_path),
        "attachment_filename": m.attachment_filename,
        "attachment_mime": m.attachment_mime,
        "attachment_size": m.attachment_size,
        "created_at": m.created_at.isoformat(),
    } for m in rows]


@router.post("/communications/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
def send_thread_message(thread_id:str,data:CommunicationMessageCreate,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    t = _thread_for_user(thread_id, current_user, db)
    if current_user.role not in {UserRole.recruiter,UserRole.institution_admin}: raise HTTPException(status_code=403,detail="Not permitted")
    m=CommunicationMessage(thread_id=t.id,sender_user_id=current_user.id,message=data.message);db.add(m);db.commit();db.refresh(m);return {"id":m.id,"message":m.message,"created_at":m.created_at.isoformat()}


@router.post("/communications/{thread_id}/attachments", status_code=status.HTTP_201_CREATED)
async def send_thread_attachment(
    thread_id: str,
    file: UploadFile = File(...),
    message: str = "Shared a placement document.",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = _thread_for_user(thread_id, current_user, db)
    if current_user.role not in {UserRole.recruiter, UserRole.institution_admin}:
        raise HTTPException(status_code=403, detail="Not permitted")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Attachment must be 10 MB or smaller")
    ext = Path(file.filename or "attachment").suffix.lower()
    allowed = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported attachment type. Use PDF, DOCX, XLSX, CSV, TXT, PNG, or JPG")
    mime_type = validate_upload_signature(raw, ext)
    path = settings.upload_dir.parent / "communication-attachments" / t.id / f"{secrets.token_hex(12)}{ext}"
    original_name = safe_upload_filename(file.filename, f"attachment{ext}")
    reference = save_file(
        db, category="communication-attachment", original_filename=original_name, mime_type=mime_type, data=raw, local_path=path
    )
    m = CommunicationMessage(
        thread_id=t.id,
        sender_user_id=current_user.id,
        message=(message or "Shared a placement document.")[:10000],
        attachment_path=reference,
        attachment_filename=original_name,
        attachment_mime=mime_type,
        attachment_size=len(raw),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "message": m.message, "attachment_filename": m.attachment_filename, "attachment_size": m.attachment_size, "created_at": m.created_at.isoformat()}


@router.get("/communications/{thread_id}/messages/{message_id}/attachment")
def download_thread_attachment(thread_id: str, message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _thread_for_user(thread_id, current_user, db)
    m = db.query(CommunicationMessage).filter(CommunicationMessage.id == message_id, CommunicationMessage.thread_id == t.id).first()
    if not m or not m.attachment_path:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return file_download_response(
        db, m.attachment_path, filename=m.attachment_filename or "attachment",
        media_type=m.attachment_mime or "application/octet-stream"
    )


# -----------------------------------------------------------------------------
# Priority 19: Confidential incident reporting
# -----------------------------------------------------------------------------
@router.get("/incidents")
def list_incidents(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if current_user.role==UserRole.student:
        s=_student(current_user,db);rows=db.query(IncidentReport).filter(IncidentReport.student_id==s.id).order_by(IncidentReport.created_at.desc()).all()
    elif current_user.role==UserRole.institution_admin:
        rows=db.query(IncidentReport).filter(IncidentReport.organization_id==current_user.organization_id).order_by(IncidentReport.created_at.desc()).all()
    else: raise HTTPException(status_code=403,detail="Incident reports are limited to students and institution teams")
    return [{"id":x.id,"category":x.category,"description":x.description,"status":x.status,"confidential":x.confidential,"recruiter_id":x.recruiter_id,"job_id":x.job_id,"resolution_notes":x.resolution_notes,"created_at":x.created_at.isoformat()} for x in rows]


@router.post("/incidents",status_code=status.HTTP_201_CREATED)
def create_incident(data:IncidentReportCreate,current_user:User=Depends(require_student),db:Session=Depends(get_db)):
    s=_student(current_user,db)
    job = None
    if data.job_id:
        job = db.query(Job).filter(Job.id == data.job_id).first()
        applied = db.query(Application).filter(Application.student_id == s.id, Application.job_id == data.job_id).first()
        if not job or not (job.target_organization_id == s.organization_id or applied):
            raise HTTPException(status_code=404, detail="Job is not linked to this student's placement activity")
    if data.recruiter_id:
        recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.id == data.recruiter_id).first()
        linked = bool(recruiter and (
            recruiter.provisioned_by_organization_id == s.organization_id or
            db.query(Job).filter(Job.recruiter_id == recruiter.id, Job.target_organization_id == s.organization_id).first() or
            db.query(Application).join(Job, Application.job_id == Job.id).filter(Application.student_id == s.id, Job.recruiter_id == recruiter.id).first()
        ))
        if not linked:
            raise HTTPException(status_code=404, detail="Recruiter is not linked to this student's placement activity")
        if job and job.recruiter_id != recruiter.id:
            raise HTTPException(status_code=400, detail="Recruiter and job do not match")
    x=IncidentReport(organization_id=s.organization_id,student_id=s.id,recruiter_id=data.recruiter_id,job_id=data.job_id,category=data.category,description=data.description,confidential=data.confidential);db.add(x)
    admins=db.query(User).filter(User.organization_id==s.organization_id,User.role==UserRole.institution_admin).all()
    for u in admins:create_notification(db,u.id,"Confidential student incident reported",f"A student submitted a {data.category} report for placement-office review.",organization_id=s.organization_id,category="incident",priority="high",link="incidents")
    db.commit();db.refresh(x);return {"id":x.id,"status":x.status}


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id:str,data:IncidentStatusUpdate,current_user:User=Depends(require_institution_admin),db:Session=Depends(get_db)):
    x=db.query(IncidentReport).filter(IncidentReport.id==incident_id,IncidentReport.organization_id==current_user.organization_id).first();
    if not x:raise HTTPException(status_code=404,detail="Incident not found")
    x.status=data.status;x.resolution_notes=data.resolution_notes;db.commit();return {"id":x.id,"status":x.status}


_DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")
_LEADING_CONTROL_CHARS = ("\t", "\r", "\n")
def spreadsheet_safe_cell(value: Any) -> Any:
    """Neutralize spreadsheet formula execution while preserving non-string values.

    CSV and XLSX consumers such as Excel may interpret attacker-controlled text beginning
    with formula markers as executable formulas. Prefix risky strings with an apostrophe,
    including values where spaces/control characters precede the formula marker.
    """
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if value.startswith(_LEADING_CONTROL_CHARS) or stripped.startswith(_DANGEROUS_FORMULA_PREFIXES):
        return "'" + value
    return value
def _safe_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [[spreadsheet_safe_cell(cell) for cell in row] for row in rows]
def _institution_report_rows(org_id: str, kind: str, db: Session) -> tuple[list[str], list[list[Any]]]:
    """Return report rows whose company/job evidence actually belongs to this institution.

    Public jobs are platform-wide. They belong in an institution participation report only
    after one of that institution's students applies. Campus-targeted jobs are included even
    before the first application. Other report kinds retain the established report builder.
    """
    if kind not in {"company-participation", "recruiter-activity"}:
        return _report_rows(org_id, kind, db)

    student_ids = [
        row[0]
        for row in db.query(StudentProfile.id).filter(StudentProfile.organization_id == org_id).all()
    ]
    applications = (
        db.query(Application).filter(Application.student_id.in_(student_ids)).all()
        if student_ids else []
    )
    applied_job_ids = {application.job_id for application in applications if application.job_id}

    relevant_jobs = db.query(Job).filter(Job.target_organization_id == org_id).all()
    relevant_job_ids = {job.id for job in relevant_jobs}
    missing_applied_ids = applied_job_ids - relevant_job_ids
    if missing_applied_ids:
        relevant_jobs.extend(db.query(Job).filter(Job.id.in_(missing_applied_ids)).all())
        relevant_job_ids.update(missing_applied_ids)

    application_count_by_job: dict[str, int] = {}
    for application in applications:
        if application.job_id in relevant_job_ids:
            application_count_by_job[application.job_id] = application_count_by_job.get(application.job_id, 0) + 1

    if kind == "company-participation":
        company: dict[str, dict[str, int]] = {}
        for job in relevant_jobs:
            name = job.recruiter.company_name if job.recruiter and job.recruiter.company_name else "Company"
            bucket = company.setdefault(name, {"jobs": 0, "applications": 0, "offers": 0})
            bucket["jobs"] += 1
            bucket["applications"] += application_count_by_job.get(job.id, 0)

        offers = (
            db.query(Offer)
            .join(Application, Offer.application_id == Application.id)
            .filter(Application.student_id.in_(student_ids))
            .all()
            if student_ids else []
        )
        for offer in offers:
            name = offer.company_name or "Company"
            company.setdefault(name, {"jobs": 0, "applications": 0, "offers": 0})["offers"] += 1

        headers = ["Company", "Jobs / drives", "Applications", "Offers"]
        rows = [
            [name, values["jobs"], values["applications"], values["offers"]]
            for name, values in sorted(company.items(), key=lambda item: item[0].lower())
        ]
        return headers, rows

    recruiter_ids = {
        row[0]
        for row in db.query(RecruiterProfile.id).filter(
            RecruiterProfile.provisioned_by_organization_id == org_id
        ).all()
    }
    recruiter_ids.update(job.recruiter_id for job in relevant_jobs if job.recruiter_id)
    recruiters = (
        db.query(RecruiterProfile).filter(RecruiterProfile.id.in_(recruiter_ids)).all()
        if recruiter_ids else []
    )
    jobs_by_recruiter: dict[str, list[Job]] = {}
    for job in relevant_jobs:
        if job.recruiter_id:
            jobs_by_recruiter.setdefault(job.recruiter_id, []).append(job)

    headers = [
        "Company",
        "Recruiter",
        "Verified",
        "Jobs",
        "Applications",
        "Successful placements",
        "Verification confidence",
    ]
    rows = []
    for recruiter in sorted(recruiters, key=lambda item: (item.company_name or "").lower()):
        recruiter_jobs = jobs_by_recruiter.get(recruiter.id, [])
        app_count = sum(application_count_by_job.get(job.id, 0) for job in recruiter_jobs)
        rows.append([
            recruiter.company_name,
            recruiter.full_name,
            "Yes" if recruiter.is_verified else "No",
            len(recruiter_jobs),
            app_count,
            recruiter.previous_successful_placements,
            recruiter.company_verification_confidence,
        ])
    return headers, rows


# -----------------------------------------------------------------------------
# Priority 20: Institution reports (CSV/XLSX/PDF)
# -----------------------------------------------------------------------------
def _report_rows(org_id: str, kind: str, db: Session) -> tuple[list[str], list[list[Any]]]:
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org_id).order_by(StudentProfile.full_name.asc()).all()
    student_ids = [s.id for s in students]
    apps = db.query(Application).filter(Application.student_id.in_(student_ids)).all() if student_ids else []
    offers = db.query(Offer).join(Application, Offer.application_id == Application.id).filter(Application.student_id.in_(student_ids)).all() if student_ids else []

    if kind == "placement-report":
        headers = ["Student", "Email", "Department", "Batch", "CGPA", "Applications", "Offers", "Placement status"]
        app_count = {}
        offer_count = {}
        for a in apps: app_count[a.student_id] = app_count.get(a.student_id, 0) + 1
        for o in offers:
            a = db.query(Application).filter(Application.id == o.application_id).first()
            if a: offer_count[a.student_id] = offer_count.get(a.student_id, 0) + 1
        rows = [[s.full_name, s.user.email if s.user else "", s.branch, s.graduation_year, s.cgpa, app_count.get(s.id, 0), offer_count.get(s.id, 0), s.placement_status] for s in students]
    elif kind == "department-placement":
        buckets = {}
        for s in students:
            b = s.branch or "Unknown"
            x = buckets.setdefault(b, {"total": 0, "placed": 0, "offers": 0})
            x["total"] += 1
            if s.placement_status == "placed": x["placed"] += 1
        for o in offers:
            a = db.query(Application).filter(Application.id == o.application_id).first()
            if a and a.student:
                buckets.setdefault(a.student.branch or "Unknown", {"total":0,"placed":0,"offers":0})["offers"] += 1
        headers = ["Department", "Students", "Placed", "Placement rate %", "Offers"]
        rows = [[b, x["total"], x["placed"], round(x["placed"] / x["total"] * 100, 1) if x["total"] else 0, x["offers"]] for b, x in sorted(buckets.items())]
    elif kind == "company-participation":
        jobs = db.query(Job).filter(or_(Job.target_organization_id == org_id, Job.visibility == "public")).all()
        company = {}
        for j in jobs:
            name = j.recruiter.company_name if j.recruiter else "Company"
            x = company.setdefault(name, {"jobs":0,"applications":0,"offers":0})
            x["jobs"] += 1
            x["applications"] += sum(1 for a in j.applications if a.student_id in student_ids)
        for o in offers:
            company.setdefault(o.company_name,{"jobs":0,"applications":0,"offers":0})["offers"] += 1
        headers = ["Company", "Jobs / drives", "Applications", "Offers"]
        rows = [[name, x["jobs"], x["applications"], x["offers"]] for name, x in sorted(company.items())]
    elif kind == "unplaced-students":
        headers = ["Student", "Email", "Branch", "Batch", "CGPA", "Placement status"]
        rows = [[s.full_name, s.user.email if s.user else "", s.branch, s.graduation_year, s.cgpa, s.placement_status] for s in students if s.placement_status != "placed"]
    elif kind == "offer-register":
        headers = ["Student", "Company", "Role", "CTC LPA", "Fixed LPA", "Variable LPA", "Status", "Joining date"]
        rows = []
        for o in offers:
            a = db.query(Application).filter(Application.id == o.application_id).first()
            rows.append([a.student.full_name if a and a.student else "", o.company_name, o.role, o.ctc_lpa, o.fixed_pay_lpa, o.variable_pay_lpa, o.status, o.joining_date.date().isoformat() if o.joining_date else ""])
    elif kind == "internship-report":
        internship_apps = [a for a in apps if a.job and "intern" in (a.job.job_type or "").lower()]
        headers = ["Student", "Company", "Role", "Status", "Applied on"]
        rows = [[a.student.full_name if a.student else "", a.job.recruiter.company_name if a.job and a.job.recruiter else "", a.job.title if a.job else "", a.status.value if hasattr(a.status,"value") else a.status, a.applied_at.date().isoformat() if a.applied_at else ""] for a in internship_apps]
    elif kind == "recruiter-activity":
        recruiters = db.query(RecruiterProfile).filter(or_(RecruiterProfile.provisioned_by_organization_id == org_id, RecruiterProfile.jobs.any(Job.target_organization_id == org_id))).all()
        headers = ["Company", "Recruiter", "Verified", "Jobs", "Applications", "Successful placements", "Verification confidence"]
        rows = []
        for r in recruiters:
            r_jobs = [j for j in r.jobs if j.target_organization_id == org_id or j.visibility == "public"]
            app_count = sum(sum(1 for a in j.applications if a.student_id in student_ids) for j in r_jobs)
            rows.append([r.company_name, r.full_name, "Yes" if r.is_verified else "No", len(r_jobs), app_count, r.previous_successful_placements, r.company_verification_confidence])
    else:
        raise HTTPException(status_code=404, detail="Unknown report. Use placement-report, department-placement, company-participation, unplaced-students, offer-register, internship-report or recruiter-activity")
    return headers, rows


@router.get("/reports/{kind}.{fmt}")
def export_report(
    kind: str,
    fmt: str,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Export institution-scoped reports with spreadsheet-formula neutralization."""
    org = _org_for_user(current_user, db)
    headers, rows = _institution_report_rows(org.id, kind, db)
    fmt = fmt.lower()

    if fmt == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerows(_safe_rows(rows))
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.csv"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
        except Exception as exc:
            raise HTTPException(status_code=503, detail="XLSX export dependency unavailable") from exc
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "PlaceAI Report"
        worksheet.append(headers)
        for row in _safe_rows(rows):
            worksheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.xlsx"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    if fmt == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PDF export dependency unavailable") from exc
        output = io.BytesIO()
        pdf = canvas.Canvas(output, pagesize=A4)
        _width, height = A4
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, height - 40, f"{org.name} — {kind.replace('-', ' ').title()}")
        y = height - 68
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, y, " | ".join(headers))
        y -= 16
        for row in rows:
            line = " | ".join("" if cell is None else str(cell) for cell in row)
            pdf.drawString(36, y, line[:115])
            y -= 12
            if y < 40:
                pdf.showPage()
                y = height - 40
                pdf.setFont("Helvetica", 8)
        pdf.save()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}.pdf"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    raise HTTPException(status_code=400, detail="Format must be csv, xlsx or pdf")

# -----------------------------------------------------------------------------
# Priority 21: Custom institution fields
# -----------------------------------------------------------------------------
@router.get("/custom-fields")
def list_custom_fields(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    org=_org_for_user(current_user,db);rows=db.query(CustomFieldDefinition).filter(CustomFieldDefinition.organization_id==org.id,CustomFieldDefinition.is_active.is_(True)).order_by(CustomFieldDefinition.label.asc()).all();return [{"id":x.id,"entity_type":x.entity_type,"label":x.label,"field_key":x.field_key,"field_type":x.field_type,"required":x.required,"options":x.options} for x in rows]


@router.post("/custom-fields",status_code=status.HTTP_201_CREATED)
def create_custom_field(data:CustomFieldCreate,current_user:User=Depends(require_institution_admin),db:Session=Depends(get_db)):
    org=_org_for_user(current_user,db);x=CustomFieldDefinition(organization_id=org.id,entity_type=data.entity_type,label=data.label,field_key=data.field_key,field_type=data.field_type,required=data.required);x.options=data.options;db.add(x);db.commit();db.refresh(x);return {"id":x.id,"label":x.label,"field_key":x.field_key,"field_type":x.field_type,"required":x.required,"options":x.options}


@router.get("/custom-fields/values/{student_id}")
def get_custom_values(student_id:str,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if current_user.role==UserRole.student:
        s=_student(current_user,db)
        if s.id!=student_id:raise HTTPException(status_code=403,detail="Not permitted")
    elif current_user.role==UserRole.institution_admin:
        s=db.query(StudentProfile).filter(StudentProfile.id==student_id,StudentProfile.organization_id==current_user.organization_id).first()
        if not s:raise HTTPException(status_code=404,detail="Student not found")
    else:raise HTTPException(status_code=403,detail="Not permitted")
    rows=db.query(CustomFieldValue).filter(CustomFieldValue.student_id==student_id).all();defs={d.id:d for d in db.query(CustomFieldDefinition).filter(CustomFieldDefinition.organization_id==s.organization_id).all()};return {defs[v.definition_id].field_key:v.value_text for v in rows if v.definition_id in defs}


@router.put("/custom-fields/values/{student_id}")
def set_custom_values(student_id:str,data:CustomFieldValueUpdate,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if current_user.role==UserRole.student:
        s=_student(current_user,db)
        if s.id!=student_id:raise HTTPException(status_code=403,detail="Not permitted")
    elif current_user.role==UserRole.institution_admin:
        s=db.query(StudentProfile).filter(StudentProfile.id==student_id,StudentProfile.organization_id==current_user.organization_id).first()
        if not s:raise HTTPException(status_code=404,detail="Student not found")
    else:raise HTTPException(status_code=403,detail="Not permitted")
    defs=db.query(CustomFieldDefinition).filter(CustomFieldDefinition.organization_id==s.organization_id).all();by_key={d.field_key:d for d in defs}
    for key,value in data.values.items():
        d=by_key.get(key)
        if not d:continue
        row=db.query(CustomFieldValue).filter(CustomFieldValue.definition_id==d.id,CustomFieldValue.student_id==s.id).first() or CustomFieldValue(definition_id=d.id,student_id=s.id)
        row.value_text=str(value);db.add(row)
    db.commit();return {"saved":True}


# -----------------------------------------------------------------------------
# Priority 22: Unified placement calendar
# -----------------------------------------------------------------------------
@router.get("/calendar")
def placement_calendar(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    org=_org_for_user(current_user,db);events=[]
    for d in db.query(PlacementDrive).filter(PlacementDrive.organization_id==org.id).all():
        if d.registration_deadline:events.append({"type":"registration_deadline","title":f"{d.title} registration closes","at":d.registration_deadline.isoformat(),"view":"drives"})
        if d.event_date:events.append({"type":"placement_drive","title":d.title,"at":d.event_date.isoformat(),"view":"drives"})
    for iv in db.query(InterviewSchedule).all():
        app=db.query(Application).filter(Application.id==iv.application_id).first()
        if app and app.student and app.student.organization_id==org.id and _application_access(current_user,app,db):events.append({"type":"interview","title":f"{iv.round_name} · {app.job.title}","at":iv.scheduled_at.isoformat(),"view":"interviews"})
    for a in db.query(Announcement).filter(Announcement.organization_id==org.id).all():
        if a.starts_at:events.append({"type":"announcement","title":a.title,"at":a.starts_at.isoformat(),"view":"announcements"})
    for o in db.query(Offer).all():
        app=db.query(Application).filter(Application.id==o.application_id).first()
        if o.joining_date and app and app.student and app.student.organization_id==org.id and _application_access(current_user,app,db):events.append({"type":"joining","title":f"Joining · {o.company_name}","at":o.joining_date.isoformat(),"view":"offers"})
    events.sort(key=lambda x:x["at"]);return events


# -----------------------------------------------------------------------------
# Priority 23: Profile approval workflow
# -----------------------------------------------------------------------------
@router.get("/profile-change-requests")
def list_profile_change_requests(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    if current_user.role==UserRole.student:
        s=_student(current_user,db);rows=db.query(ProfileChangeRequest).filter(ProfileChangeRequest.student_id==s.id).order_by(ProfileChangeRequest.created_at.desc()).all()
    elif current_user.role==UserRole.institution_admin:
        rows=db.query(ProfileChangeRequest).filter(ProfileChangeRequest.organization_id==current_user.organization_id).order_by(ProfileChangeRequest.created_at.desc()).all()
    else:raise HTTPException(status_code=403,detail="Not permitted")
    result=[]
    for r in rows:
        s=db.query(StudentProfile).filter(StudentProfile.id==r.student_id).first();result.append({"id":r.id,"student_id":r.student_id,"student_name":s.full_name if s else None,"field_name":r.field_name,"old_value":r.old_value,"new_value":r.new_value,"status":r.status,"created_at":r.created_at.isoformat()})
    return result


@router.patch("/profile-change-requests/{request_id}")
def review_profile_change(request_id:str,data:ProfileChangeReview,current_user:User=Depends(require_institution_admin),db:Session=Depends(get_db)):
    r=db.query(ProfileChangeRequest).filter(ProfileChangeRequest.id==request_id,ProfileChangeRequest.organization_id==current_user.organization_id,ProfileChangeRequest.status=="pending").first();
    if not r:raise HTTPException(status_code=404,detail="Pending change request not found")
    s=db.query(StudentProfile).filter(StudentProfile.id==r.student_id).first();
    if not s:raise HTTPException(status_code=404,detail="Student not found")
    if data.status=="approved":
        value=r.new_value
        if r.field_name in {"graduation_year","active_backlogs","historical_backlogs","academic_gap_months"}:value=int(value) if value not in {None,""} else None
        elif r.field_name in {"cgpa","tenth_percentage","twelfth_percentage","diploma_percentage"}:value=float(value) if value not in {None,""} else None
        setattr(s,r.field_name,value);s.is_verified=True
    r.status=data.status;r.reviewed_by_user_id=current_user.id;r.reviewed_at=utcnow();create_notification(db,s.user_id,f"Profile change {data.status}",f"Your request to change {r.field_name.replace('_',' ')} was {data.status}.",organization_id=s.organization_id,category="profile",link="profile");db.commit();return {"id":r.id,"status":r.status}
