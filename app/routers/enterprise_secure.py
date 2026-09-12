from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_student
from app.models import (
    Announcement,
    Application,
    AttendanceRecord,
    AttendanceSession,
    CommunicationMessage,
    CommunicationThread,
    DriveStage,
    DriveStatus,
    InterviewSchedule,
    Job,
    Notification,
    Offer,
    Organization,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.placement_access import available_drives_for_student, drive_is_available_to_student, job_is_visible_to_student
from app.services import create_notification, evaluate_drive_eligibility

router = APIRouter(prefix="/enterprise", tags=["Enterprise Placement Operations"])


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _student(user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _verified_student(user: User, db: Session) -> StudentProfile:
    profile = _student(user, db)
    if not profile.is_verified or not profile.organization_id:
        raise HTTPException(status_code=403, detail="Institution verification is required for this campus workspace")
    org = db.query(Organization).filter(
        Organization.id == profile.organization_id,
        Organization.is_active.is_(True),
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Institution is inactive or unavailable")
    return profile


def _recruiter(user: User, db: Session) -> RecruiterProfile:
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter profile not found")
    return profile


def _active_org_for_operator(user: User, db: Session) -> Organization:
    org_id = user.organization_id
    if not org_id and user.role == UserRole.recruiter:
        recruiter = _recruiter(user, db)
        org_id = recruiter.provisioned_by_organization_id
    if not org_id:
        raise HTTPException(status_code=403, detail="Account is not linked to an institution")
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.is_active.is_(True),
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Institution is inactive or unavailable")
    return org


def _drive_payload(drive: PlacementDrive) -> dict:
    return {
        "id": drive.id,
        "title": drive.title,
        "job_id": drive.job_id,
        "job_title": drive.job.title if drive.job else None,
        "company_name": drive.job.recruiter.company_name if drive.job and drive.job.recruiter else None,
        "status": drive.status.value if hasattr(drive.status, "value") else str(drive.status),
        "event_date": drive.event_date.isoformat() if drive.event_date else None,
        "registration_deadline": drive.registration_deadline.isoformat() if drive.registration_deadline else None,
    }


def _application_access(user: User, application: Application, db: Session) -> bool:
    if user.role == UserRole.student:
        return application.student_id == _student(user, db).id
    if user.role == UserRole.recruiter:
        return bool(application.job and application.job.recruiter_id == _recruiter(user, db).id)
    if user.role == UserRole.institution_admin:
        return bool(application.student and application.student.organization_id == user.organization_id)
    return user.role == UserRole.platform_admin


def _announcement_active(row: Announcement, now: datetime) -> bool:
    starts_at = row.starts_at
    expires_at = row.expires_at
    if starts_at and starts_at > now:
        return False
    if expires_at and expires_at <= now:
        return False
    return True


def _announcement_matches_student(row: Announcement, student: StudentProfile, db: Session) -> bool:
    values = row.audience_value
    if row.audience_type == "all_students":
        return True
    if row.audience_type == "branch":
        return (student.branch or "").lower() in {str(x).lower() for x in values.get("branches", [])}
    if row.audience_type == "batch":
        return student.graduation_year in values.get("graduation_years", [])
    if row.audience_type == "specific_students":
        return student.id in values.get("student_ids", [])
    if row.audience_type == "eligible_students":
        drive_id = values.get("drive_id")
        drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first() if drive_id else None
        return bool(
            drive
            and drive_is_available_to_student(drive, student)
            and evaluate_drive_eligibility(student, drive, db)["eligible"]
        )
    if row.audience_type == "drive_participants":
        drive_id = values.get("drive_id")
        return bool(
            drive_id
            and db.query(Application).filter(
                Application.student_id == student.id,
                Application.drive_id == drive_id,
            ).first()
        )
    return False


def _announcement_payload(row: Announcement, now: datetime) -> dict:
    if row.expires_at and row.expires_at <= now:
        state = "expired"
    elif row.starts_at and row.starts_at > now:
        state = "scheduled"
    else:
        state = "active"
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
        "delivery_state": state,
    }


def _ensure_announcement_notification(db: Session, row: Announcement, student: StudentProfile) -> bool:
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


@router.get("/drives")
def enterprise_drives(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.student:
        student = _student(current_user, db)
        rows = available_drives_for_student(student, db)
    elif current_user.role == UserRole.institution_admin:
        org = _active_org_for_operator(current_user, db)
        rows = db.query(PlacementDrive).filter(
            PlacementDrive.organization_id == org.id
        ).order_by(PlacementDrive.created_at.desc()).limit(500).all()
    elif current_user.role == UserRole.recruiter:
        recruiter = _recruiter(current_user, db)
        rows = db.query(PlacementDrive).join(Job, PlacementDrive.job_id == Job.id).filter(
            Job.recruiter_id == recruiter.id
        ).order_by(PlacementDrive.created_at.desc()).limit(500).all()
    elif current_user.role == UserRole.platform_admin:
        rows = db.query(PlacementDrive).order_by(PlacementDrive.created_at.desc()).limit(500).all()
    else:
        raise HTTPException(status_code=403, detail="Not permitted")
    return [_drive_payload(drive) for drive in rows]


@router.get("/drives/{drive_id}/pipeline")
def get_pipeline(drive_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    if current_user.role == UserRole.student:
        student = _student(current_user, db)
        if not drive_is_available_to_student(drive, student):
            raise HTTPException(status_code=404, detail="Drive not found")
    elif current_user.role == UserRole.institution_admin:
        if current_user.organization_id != drive.organization_id:
            raise HTTPException(status_code=404, detail="Drive not found")
    elif current_user.role == UserRole.recruiter:
        if not drive.job or drive.job.recruiter_id != _recruiter(current_user, db).id:
            raise HTTPException(status_code=404, detail="Drive not found")
    elif current_user.role != UserRole.platform_admin:
        raise HTTPException(status_code=403, detail="Not permitted")
    stages = db.query(DriveStage).filter(
        DriveStage.drive_id == drive.id
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


@router.get("/drives/{drive_id}/eligibility")
def advanced_eligibility(
    drive_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = _verified_student(current_user, db)
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive or not drive_is_available_to_student(drive, student):
        raise HTTPException(status_code=404, detail="Drive not found or no longer available")
    return evaluate_drive_eligibility(student, drive, db)


@router.get("/communications")
def list_threads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.institution_admin:
        org = _active_org_for_operator(current_user, db)
        query = db.query(CommunicationThread).filter(CommunicationThread.organization_id == org.id)
    elif current_user.role == UserRole.recruiter:
        org = _active_org_for_operator(current_user, db)
        recruiter = _recruiter(current_user, db)
        query = db.query(CommunicationThread).filter(
            CommunicationThread.organization_id == org.id,
            CommunicationThread.recruiter_profile_id == recruiter.id,
        )
    else:
        raise HTTPException(status_code=403, detail="Communication threads are limited to placement teams and recruiters")
    rows = query.order_by(CommunicationThread.created_at.desc()).limit(500).all()
    return [
        {
            "id": row.id,
            "subject": row.subject,
            "status": row.status,
            "drive_id": row.drive_id,
            "recruiter_profile_id": row.recruiter_profile_id,
            "message_count": db.query(CommunicationMessage).filter(CommunicationMessage.thread_id == row.id).count(),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/announcements")
def list_announcements(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.institution_admin:
        org = _active_org_for_operator(current_user, db)
        rows = db.query(Announcement).filter(
            Announcement.organization_id == org.id
        ).order_by(Announcement.created_at.desc()).limit(500).all()
        now = _utc_naive_now()
        return [_announcement_payload(row, now) for row in rows]
    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Announcements are limited to institution teams and verified students")

    student = _verified_student(current_user, db)
    now = _utc_naive_now()
    rows = db.query(Announcement).filter(
        Announcement.organization_id == student.organization_id
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


@router.get("/attendance/sessions")
def list_attendance_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.institution_admin:
        org = _active_org_for_operator(current_user, db)
        rows = db.query(AttendanceSession).filter(
            AttendanceSession.organization_id == org.id
        ).order_by(AttendanceSession.created_at.desc()).limit(500).all()
        return [
            {
                "id": row.id,
                "title": row.title,
                "session_type": row.session_type,
                "drive_id": row.drive_id,
                "starts_at": row.starts_at.isoformat() if row.starts_at else None,
                "closes_at": row.closes_at.isoformat() if row.closes_at else None,
                "is_active": row.is_active,
                "checkins": db.query(AttendanceRecord).filter(AttendanceRecord.session_id == row.id).count(),
            }
            for row in rows
        ]
    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Attendance sessions are limited to institution teams and verified students")

    student = _verified_student(current_user, db)
    now = _utc_naive_now()
    rows = db.query(AttendanceSession).filter(
        AttendanceSession.organization_id == student.organization_id,
        AttendanceSession.is_active.is_(True),
    ).order_by(AttendanceSession.created_at.desc()).limit(200).all()
    visible = [
        row for row in rows
        if (row.closes_at is None or row.closes_at >= now)
    ]
    return [
        {
            "id": row.id,
            "title": row.title,
            "session_type": row.session_type,
            "drive_id": row.drive_id,
            "starts_at": row.starts_at.isoformat() if row.starts_at else None,
            "closes_at": row.closes_at.isoformat() if row.closes_at else None,
            "is_active": row.is_active,
        }
        for row in visible
    ]


@router.post("/attendance/check-in")
def attendance_checkin(
    token: str = Query(min_length=16, max_length=200),
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = _verified_student(current_user, db)
    session = db.query(AttendanceSession).filter(
        AttendanceSession.token == token,
        AttendanceSession.is_active.is_(True),
        AttendanceSession.organization_id == student.organization_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Attendance session not found or inactive")
    now = _utc_naive_now()
    if session.starts_at and now < session.starts_at:
        raise HTTPException(status_code=425, detail="Attendance check-in has not opened yet")
    if session.closes_at and now > session.closes_at:
        raise HTTPException(status_code=410, detail="Attendance check-in has closed")
    if session.drive_id:
        drive = db.query(PlacementDrive).filter(
            PlacementDrive.id == session.drive_id,
            PlacementDrive.organization_id == student.organization_id,
        ).first()
        if (
            not drive
            or drive.status == DriveStatus.draft
            or not drive.job
            or drive.job.visibility != "campus"
            or drive.job.target_organization_id != student.organization_id
        ):
            raise HTTPException(status_code=404, detail="Attendance session is not linked to an available campus event")
    record = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == session.id,
        AttendanceRecord.student_id == student.id,
    ).first()
    if not record:
        record = AttendanceRecord(session_id=session.id, student_id=student.id)
        db.add(record)
        db.commit()
        db.refresh(record)
    return {
        "checked_in": True,
        "session": session.title,
        "checked_in_at": record.checked_in_at.isoformat(),
    }


@router.get("/search")
def workspace_search(
    q: str = Query(min_length=1, max_length=120),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query_text = q.strip()
    term = f"%{query_text}%"
    lowered = query_text.lower()
    results: list[dict] = []

    def job_matches(job: Job) -> bool:
        values = [
            job.title,
            job.description,
            job.location,
            job.job_type,
            job.salary_range,
            job.experience_required,
            job.recruiter.company_name if job.recruiter else "",
            *(job.required_skills or []),
            *(job.preferred_roles or []),
        ]
        return lowered in " ".join(str(value) for value in values if value).lower()

    if current_user.role in {UserRole.institution_admin, UserRole.platform_admin}:
        org_id = current_user.organization_id
        student_query = db.query(StudentProfile).filter(or_(
            StudentProfile.full_name.ilike(term),
            StudentProfile.branch.ilike(term),
            StudentProfile.degree.ilike(term),
        ))
        if org_id:
            student_query = student_query.filter(StudentProfile.organization_id == org_id)
        for student in student_query.limit(8):
            results.append({
                "type": "student",
                "id": student.id,
                "title": student.full_name or "Student",
                "subtitle": f"{student.branch or ''} · {student.graduation_year or ''}",
                "view": "students",
            })
        job_query = db.query(Job)
        if org_id:
            job_query = job_query.filter(or_(Job.target_organization_id == org_id, Job.visibility == "public"))
        for job in (candidate for candidate in job_query.order_by(Job.created_at.desc()).limit(500).all() if job_matches(candidate)):
            results.append({
                "type": "job",
                "id": job.id,
                "title": job.title,
                "subtitle": job.recruiter.company_name if job.recruiter else "Company",
                "view": "jobs",
            })
            if sum(1 for item in results if item["type"] == "job") >= 8:
                break
    elif current_user.role == UserRole.recruiter:
        recruiter = _recruiter(current_user, db)
        matched_jobs = [job for job in recruiter.jobs if job_matches(job)]
        for job in sorted(matched_jobs, key=lambda item: item.created_at, reverse=True)[:8]:
            results.append({"type": "job", "id": job.id, "title": job.title, "subtitle": job.location or "", "view": "jobs"})
        ids = {app.student_id for job in recruiter.jobs for app in job.applications}
        if ids:
            candidates = db.query(StudentProfile).filter(StudentProfile.id.in_(ids)).limit(300).all()
            candidates = [
                student for student in candidates
                if lowered in " ".join([
                    student.full_name or "",
                    student.branch or "",
                    student.degree or "",
                    " ".join(student.skills or []),
                ]).lower()
            ]
            for student in candidates[:8]:
                results.append({"type": "candidate", "id": student.id, "title": student.full_name or "Candidate", "subtitle": student.branch or "", "view": "candidates"})
    elif current_user.role == UserRole.student:
        student = _student(current_user, db)
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(500).all()
        visible = [job for job in jobs if job_is_visible_to_student(student, job, db)]
        for job in (candidate for candidate in visible if job_matches(candidate)):
            results.append({
                "type": "opportunity",
                "id": job.id,
                "title": job.title,
                "subtitle": f"{job.recruiter.company_name if job.recruiter else 'Company'} · {job.location or 'Flexible location'}",
                "view": "opportunities",
            })
            if len(results) >= 10:
                break
    else:
        raise HTTPException(status_code=403, detail="Not permitted")
    return results[:20]


@router.get("/calendar")
def placement_calendar(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    events: list[dict] = []

    if current_user.role == UserRole.student:
        student = _verified_student(current_user, db)
        drives = available_drives_for_student(student, db)
        for drive in drives:
            if drive.registration_deadline:
                events.append({"type": "registration_deadline", "title": f"{drive.title} registration closes", "at": drive.registration_deadline.isoformat(), "view": "drives"})
            if drive.event_date:
                events.append({"type": "placement_drive", "title": drive.title, "at": drive.event_date.isoformat(), "view": "drives"})
        applications = db.query(Application).filter(Application.student_id == student.id).all()
        application_ids = [app.id for app in applications]
        interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(application_ids)).all() if application_ids else []
        offers = db.query(Offer).filter(Offer.application_id.in_(application_ids)).all() if application_ids else []
        announcements = db.query(Announcement).filter(Announcement.organization_id == student.organization_id).all()
        now = _utc_naive_now()
        announcements = [row for row in announcements if _announcement_active(row, now) and _announcement_matches_student(row, student, db)]
    elif current_user.role == UserRole.institution_admin:
        org = _active_org_for_operator(current_user, db)
        drives = db.query(PlacementDrive).filter(PlacementDrive.organization_id == org.id).limit(500).all()
        for drive in drives:
            if drive.registration_deadline:
                events.append({"type": "registration_deadline", "title": f"{drive.title} registration closes", "at": drive.registration_deadline.isoformat(), "view": "drives"})
            if drive.event_date:
                events.append({"type": "placement_drive", "title": drive.title, "at": drive.event_date.isoformat(), "view": "drives"})
        student_ids = [row[0] for row in db.query(StudentProfile.id).filter(StudentProfile.organization_id == org.id).all()]
        applications = db.query(Application).filter(Application.student_id.in_(student_ids)).all() if student_ids else []
        application_ids = [app.id for app in applications]
        interviews = db.query(InterviewSchedule).filter(InterviewSchedule.application_id.in_(application_ids)).all() if application_ids else []
        offers = db.query(Offer).filter(Offer.application_id.in_(application_ids)).all() if application_ids else []
        announcements = db.query(Announcement).filter(Announcement.organization_id == org.id).all()
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
        announcements = []
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
