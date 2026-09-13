from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    Announcement,
    Application,
    CustomFieldDefinition,
    InterviewSchedule,
    Offer,
    Organization,
    PlacementDrive,
    StudentProfile,
    User,
    UserRole,
)
from app.placement_access import available_drives_for_student
from app.routers.enterprise_secure import (
    _active_org_for_operator,
    _announcement_active,
    _announcement_matches_student,
    _announcement_payload,
    _application_access,
    _ensure_announcement_notification,
    _recruiter,
    _student,
    _utc_naive_now,
)

router = APIRouter(prefix="/enterprise", tags=["Enterprise Placement Operations"])


def _linked_student_organization(student: StudentProfile, db: Session) -> Organization | None:
    """Return the active linked institution without implying campus verification."""
    if not student.organization_id:
        return None
    return db.query(Organization).filter(
        Organization.id == student.organization_id,
        Organization.is_active.is_(True),
    ).first()


def _student_campus_context(student: StudentProfile, db: Session) -> Organization | None:
    """Return campus context only after the placement office verifies the student."""
    if not student.is_verified:
        return None
    return _linked_student_organization(student, db)


@router.get("/student-campus-status")
def student_campus_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Student workspace only")
    student = _student(current_user, db)
    organization = _linked_student_organization(student, db)
    linked = organization is not None
    verified = bool(linked and student.is_verified)
    return {
        "linked": linked,
        "verified": verified,
        "organization_id": organization.id if organization else None,
        "organization_name": organization.name if organization else None,
        "campus_features_available": verified,
        "message": (
            "Campus workspace verified"
            if verified
            else "Institution verification is pending"
            if linked
            else "No institution is linked to this student account"
        ),
    }


@router.get("/custom-fields")
def custom_fields_read_v2(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.student:
        student = _student(current_user, db)
        organization = _student_campus_context(student, db)
        if not organization:
            return []
    else:
        organization = _active_org_for_operator(current_user, db)
    rows = db.query(CustomFieldDefinition).filter(
        CustomFieldDefinition.organization_id == organization.id,
        CustomFieldDefinition.is_active.is_(True),
    ).order_by(CustomFieldDefinition.label.asc()).all()
    return [
        {
            "id": row.id,
            "entity_type": row.entity_type,
            "label": row.label,
            "field_key": row.field_key,
            "field_type": row.field_type,
            "required": row.required,
            "options": row.options,
        }
        for row in rows
    ]


@router.get("/announcements")
def announcements_read_v2(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.institution_admin:
        organization = _active_org_for_operator(current_user, db)
        rows = db.query(Announcement).filter(
            Announcement.organization_id == organization.id
        ).order_by(Announcement.created_at.desc()).limit(500).all()
        now = _utc_naive_now()
        return [_announcement_payload(row, now) for row in rows]

    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Announcements are limited to institution teams and students")

    student = _student(current_user, db)
    # Operational announcements are safe for an account already linked to an active
    # institution, even while placement-office verification is pending. Verification
    # still gates campus jobs, drives, eligibility and institution custom fields.
    organization = _linked_student_organization(student, db)
    if not organization:
        return []

    now = _utc_naive_now()
    rows = db.query(Announcement).filter(
        Announcement.organization_id == organization.id
    ).order_by(Announcement.created_at.desc()).limit(500).all()
    visible = [
        row for row in rows
        if _announcement_active(row, now) and _announcement_matches_student(row, student, db)
    ]
    created = False
    for row in visible:
        created = _ensure_announcement_notification(db, row, student) or created
    if created:
        db.commit()
    return [_announcement_payload(row, now) for row in visible]


@router.get("/calendar")
def placement_calendar_v2(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the user's personal calendar even before campus verification.

    Campus drives and institution announcements are added only after a student has a
    verified active institution link. Personal application interviews/offers remain
    visible because they belong to the student's own account and do not require a
    campus relationship.
    """
    events: list[dict] = []
    announcements: list[Announcement] = []

    if current_user.role == UserRole.student:
        student = _student(current_user, db)
        organization = _student_campus_context(student, db)
        drives = available_drives_for_student(student, db) if organization else []
        for drive in drives:
            if drive.registration_deadline:
                events.append({
                    "type": "registration_deadline",
                    "title": f"{drive.title} registration closes",
                    "at": drive.registration_deadline.isoformat(),
                    "view": "drives",
                })
            if drive.event_date:
                events.append({"type": "placement_drive", "title": drive.title, "at": drive.event_date.isoformat(), "view": "drives"})
        applications = db.query(Application).filter(Application.student_id == student.id).all()
        application_ids = [app.id for app in applications]
        interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(application_ids)).all() if application_ids else []
        offers = db.query(Offer).filter(Offer.application_id.in_(application_ids)).all() if application_ids else []
        if organization:
            rows = db.query(Announcement).filter(Announcement.organization_id == organization.id).all()
            now = _utc_naive_now()
            announcements = [
                row for row in rows
                if _announcement_active(row, now) and _announcement_matches_student(row, student, db)
            ]

    elif current_user.role == UserRole.institution_admin:
        organization = _active_org_for_operator(current_user, db)
        drives = db.query(PlacementDrive).filter(PlacementDrive.organization_id == organization.id).limit(500).all()
        for drive in drives:
            if drive.registration_deadline:
                events.append({"type": "registration_deadline", "title": f"{drive.title} registration closes", "at": drive.registration_deadline.isoformat(), "view": "drives"})
            if drive.event_date:
                events.append({"type": "placement_drive", "title": drive.title, "at": drive.event_date.isoformat(), "view": "drives"})
        student_ids = [row[0] for row in db.query(StudentProfile.id).filter(StudentProfile.organization_id == organization.id).all()]
        applications = db.query(Application).filter(Application.student_id.in_(student_ids)).all() if student_ids else []
        application_ids = [app.id for app in applications]
        interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(application_ids)).all() if application_ids else []
        offers = db.query(Offer).filter(Offer.application_id.in_(application_ids)).all() if application_ids else []
        announcements = db.query(Announcement).filter(Announcement.organization_id == organization.id).all()

    elif current_user.role == UserRole.recruiter:
        recruiter = _recruiter(current_user, db)
        job_ids = [job.id for job in recruiter.jobs]
        drives = db.query(PlacementDrive).filter(PlacementDrive.job_id.in_(job_ids)).limit(500).all() if job_ids else []
        for drive in drives:
            if drive.registration_deadline:
                events.append({"type": "registration_deadline", "title": f"{drive.title} registration closes", "at": drive.registration_deadline.isoformat(), "view": "drives"})
            if drive.event_date:
                events.append({"type": "placement_drive", "title": drive.title, "at": drive.event_date.isoformat(), "view": "drives"})
        applications = db.query(Application).filter(Application.job_id.in_(job_ids)).all() if job_ids else []
        application_ids = [app.id for app in applications]
        interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(application_ids)).all() if application_ids else []
        offers = db.query(Offer).filter(Offer.application_id.in_(application_ids)).all() if application_ids else []

    else:
        raise HTTPException(status_code=403, detail="Calendar is not available in this workspace")

    for interview in interviews:
        application = db.query(Application).filter(Application.id == interview.application_id).first()
        if application and _application_access(current_user, application, db):
            events.append({
                "type": "interview",
                "title": f"{interview.round_name} · {application.job.title}",
                "at": interview.scheduled_at.isoformat(),
                "view": "interviews",
            })
    for announcement in announcements:
        if announcement.starts_at:
            events.append({"type": "announcement", "title": announcement.title, "at": announcement.starts_at.isoformat(), "view": "announcements"})
    for offer in offers:
        application = db.query(Application).filter(Application.id == offer.application_id).first()
        if offer.joining_date and application and _application_access(current_user, application, db):
            events.append({"type": "joining", "title": f"Joining · {offer.company_name}", "at": offer.joining_date.isoformat(), "view": "offers"})
    events.sort(key=lambda item: item["at"])
    return events
