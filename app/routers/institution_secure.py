from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_institution_admin
from app.models import (
    Application,
    ApplicationStatus,
    ApprovalStatus,
    DriveStage,
    DriveStatus,
    Job,
    Organization,
    PlacementDrive,
    StudentProfile,
    User,
    UserRole,
)
from app.placement_access import deadline_has_passed, job_is_available
from app.schemas import (
    ApplicationOut,
    InstitutionDashboardOut,
    JobApprovalUpdate,
    JobOut,
    PlacementDriveCreate,
    PlacementDriveOut,
    PlacementDriveUpdate,
)
from app.services import application_out, create_notification, drive_out, job_out, record_audit

router = APIRouter(prefix="/institutions", tags=["Institution / TPO"])


def _org(current_user: User, db: Session) -> Organization:
    org = db.query(Organization).filter(
        Organization.id == current_user.organization_id,
        Organization.is_active.is_(True),
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Your account is not linked to an active institution")
    return org


def _campus_job_for_org(job_id: str, org: Organization, db: Session) -> Job:
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.target_organization_id == org.id,
        Job.visibility == "campus",
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Campus job not found for this institution")
    return job


def _assert_job_can_host_open_drive(job: Job) -> None:
    if not job_is_available(job) or job.visibility != "campus":
        raise HTTPException(
            status_code=400,
            detail="The campus job must be approved, active, and within its application window before opening a drive",
        )


@router.get("/dashboard", response_model=InstitutionDashboardOut)
def dashboard(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org.id).all()
    student_ids = [student.id for student in students]
    applications = (
        db.query(Application).filter(Application.student_id.in_(student_ids)).all()
        if student_ids
        else []
    )
    target_jobs = db.query(Job).filter(Job.target_organization_id == org.id).all()
    active_job_ids = {
        job.id for job in target_jobs
        if job.visibility == "campus" and job_is_available(job)
    }
    drives = db.query(PlacementDrive).filter(
        PlacementDrive.organization_id == org.id,
        PlacementDrive.status == DriveStatus.open,
    ).all()
    active_drives = [
        drive for drive in drives
        if drive.job_id in active_job_ids and not deadline_has_passed(drive.registration_deadline)
    ]
    offered_applications = [
        application for application in applications
        if application.status in {ApplicationStatus.offered, ApplicationStatus.hired}
    ]
    hired_student_ids = {
        application.student_id for application in applications
        if application.status == ApplicationStatus.hired
    }
    eligible_base = max(len(students), 1)
    return InstitutionDashboardOut(
        organization=org,
        total_students=len(students),
        verified_students=sum(1 for student in students if student.is_verified),
        active_jobs=len(active_job_ids),
        open_drives=len(active_drives),
        total_applications=len(applications),
        offers=len(offered_applications),
        hires=len(hired_student_ids),
        placement_rate=round(len(hired_student_ids) / eligible_base * 100, 1),
    )


@router.patch("/jobs/{job_id}/approval", response_model=JobOut)
def approve_job(
    job_id: str,
    data: JobApprovalUpdate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org(current_user, db)
    job = _campus_job_for_org(job_id, org, db)
    requested = ApprovalStatus(data.approval_status.value)
    if requested == ApprovalStatus.approved and deadline_has_passed(job.deadline):
        raise HTTPException(status_code=400, detail="An expired campus job cannot be approved")

    job.approval_status = requested
    job.is_active = requested == ApprovalStatus.approved
    record_audit(
        db,
        current_user,
        "institution.job.approval_changed",
        organization_id=org.id,
        entity_type="job",
        entity_id=job.id,
        metadata={"approval_status": requested.value, "title": job.title},
    )
    if job.recruiter and job.recruiter.user_id:
        create_notification(
            db,
            job.recruiter.user_id,
            f"Campus job {requested.value}",
            f"{org.name} {requested.value} your campus job: {job.title}.",
            organization_id=org.id,
            category="campus",
            priority="high" if requested == ApprovalStatus.approved else "normal",
            link="jobs",
        )
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.post("/drives", response_model=PlacementDriveOut, status_code=status.HTTP_201_CREATED)
def create_drive(
    data: PlacementDriveCreate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org(current_user, db)
    job = _campus_job_for_org(data.job_id, org, db)
    _assert_job_can_host_open_drive(job)
    if data.status.value == DriveStatus.open.value and deadline_has_passed(data.registration_deadline):
        raise HTTPException(status_code=400, detail="An open drive must have a future registration deadline")

    drive = PlacementDrive(
        organization_id=org.id,
        job_id=job.id,
        title=data.title,
        min_cgpa=data.min_cgpa,
        min_tenth_percentage=data.min_tenth_percentage,
        min_twelfth_percentage=data.min_twelfth_percentage,
        min_diploma_percentage=data.min_diploma_percentage,
        max_active_backlogs=data.max_active_backlogs,
        max_historical_backlogs=data.max_historical_backlogs,
        max_academic_gap_months=data.max_academic_gap_months,
        work_authorization_required=data.work_authorization_required,
        allow_placed_students=data.allow_placed_students,
        registration_deadline=data.registration_deadline,
        event_date=data.event_date,
        notes=data.notes,
        status=DriveStatus(data.status.value),
    )
    drive.allowed_graduation_years = data.allowed_graduation_years
    drive.allowed_branches = data.allowed_branches
    drive.required_skills = data.required_skills
    drive.required_certifications = data.required_certifications
    drive.required_documents = data.required_documents
    drive.custom_eligibility_rules = data.custom_eligibility_rules
    db.add(drive)
    db.flush()

    default_stages = [
        ("registration", "Registration", "registration"),
        ("eligibility-screening", "Eligibility Screening", "screening"),
        ("online-assessment", "Online Assessment", "assessment"),
        ("technical-round-1", "Technical Round 1", "interview"),
        ("technical-round-2", "Technical Round 2", "interview"),
        ("hr-interview", "HR Interview", "interview"),
        ("offer", "Offer", "offer"),
        ("joined", "Joined", "terminal"),
    ]
    for index, (key, name, stage_type) in enumerate(default_stages):
        db.add(DriveStage(
            drive_id=drive.id,
            stage_key=key,
            name=name,
            order_index=index,
            stage_type=stage_type,
            is_terminal=key == "joined",
        ))
    record_audit(
        db,
        current_user,
        "institution.drive.created",
        organization_id=org.id,
        entity_type="placement_drive",
        entity_id=drive.id,
        metadata={"job_id": job.id, "title": drive.title, "status": drive.status.value},
    )
    db.commit()
    db.refresh(drive)
    return drive_out(drive, db)


@router.put("/drives/{drive_id}", response_model=PlacementDriveOut)
def update_drive(
    drive_id: str,
    data: PlacementDriveUpdate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org(current_user, db)
    drive = db.query(PlacementDrive).filter(
        PlacementDrive.id == drive_id,
        PlacementDrive.organization_id == org.id,
    ).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Placement drive not found")

    changes = data.model_dump(exclude_unset=True)
    target_status = changes.get("status", drive.status)
    target_status_value = target_status.value if hasattr(target_status, "value") else str(target_status)
    target_deadline = changes.get("registration_deadline", drive.registration_deadline)
    if target_status_value == DriveStatus.open.value:
        job = _campus_job_for_org(drive.job_id, org, db)
        _assert_job_can_host_open_drive(job)
        if deadline_has_passed(target_deadline):
            raise HTTPException(status_code=400, detail="An open drive must have a future registration deadline")

    for field, value in changes.items():
        if field == "allowed_graduation_years":
            drive.allowed_graduation_years = value
        elif field == "allowed_branches":
            drive.allowed_branches = value
        elif field == "required_skills":
            drive.required_skills = value
        elif field == "required_certifications":
            drive.required_certifications = value
        elif field == "required_documents":
            drive.required_documents = value
        elif field == "custom_eligibility_rules":
            drive.custom_eligibility_rules = value
        elif field == "status":
            drive.status = DriveStatus(value.value)
        else:
            setattr(drive, field, value)
    record_audit(
        db,
        current_user,
        "institution.drive.updated",
        organization_id=org.id,
        entity_type="placement_drive",
        entity_id=drive.id,
        metadata={"title": drive.title, "status": drive.status.value},
    )
    db.commit()
    db.refresh(drive)
    return drive_out(drive, db)


@router.get("/applications", response_model=List[ApplicationOut])
def institution_applications(
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    org = _org(current_user, db)
    student_ids = [
        row[0] for row in db.query(StudentProfile.id).filter(StudentProfile.organization_id == org.id).all()
    ]
    if not student_ids:
        return []
    applications = db.query(Application).filter(
        Application.student_id.in_(student_ids)
    ).order_by(Application.applied_at.desc()).limit(3000).all()
    return [application_out(application) for application in applications]


# Load the access-request extension only after the canonical institution router
# and helper functions above are fully defined. The extension decorates this
# same router before app.app includes it, avoiding import-order side effects.
from app.routers import institution_access as _institution_access  # noqa: E402,F401
