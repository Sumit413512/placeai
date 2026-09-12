from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ApprovalStatus, DriveStatus, Job, PlacementDrive, StudentProfile


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def deadline_has_passed(value: datetime | None, *, now: datetime | None = None) -> bool:
    if value is None:
        return False
    point = now or datetime.now(timezone.utc)
    deadline = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return deadline <= point


def job_is_available(job: Job | None, *, now: datetime | None = None) -> bool:
    if job is None:
        return False
    if not job.is_active or job.approval_status != ApprovalStatus.approved:
        return False
    if deadline_has_passed(job.deadline, now=now):
        return False
    return True


def drive_is_available_to_student(
    drive: PlacementDrive | None,
    student: StudentProfile,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a campus drive may be surfaced to this student.

    This is the canonical campus-discovery boundary used across the standard student,
    mock-interview and enterprise workspaces. It intentionally requires institution
    verification, an open/non-expired drive, and a currently approved/active campus job.
    """
    if drive is None or not student.is_verified or not student.organization_id:
        return False
    if drive.organization_id != student.organization_id or drive.status != DriveStatus.open:
        return False
    if deadline_has_passed(drive.registration_deadline, now=now):
        return False

    job = drive.job
    if not job_is_available(job, now=now):
        return False
    if job.visibility != "campus":
        return False
    if job.target_organization_id != student.organization_id:
        return False
    if job.id != drive.job_id:
        return False
    return True


def available_drives_for_student(student: StudentProfile, db: Session) -> list[PlacementDrive]:
    if not student.is_verified or not student.organization_id:
        return []
    now = datetime.now(timezone.utc)
    rows = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.organization_id == student.organization_id,
            PlacementDrive.status == DriveStatus.open,
        )
        .order_by(PlacementDrive.created_at.desc())
        .all()
    )
    return [drive for drive in rows if drive_is_available_to_student(drive, student, now=now)]


def available_drive_for_job(
    student: StudentProfile,
    job: Job,
    db: Session,
) -> PlacementDrive | None:
    if not student.is_verified or not student.organization_id:
        return None
    now = datetime.now(timezone.utc)
    rows = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.job_id == job.id,
            PlacementDrive.organization_id == student.organization_id,
            PlacementDrive.status == DriveStatus.open,
        )
        .order_by(PlacementDrive.created_at.desc())
        .all()
    )
    return next(
        (drive for drive in rows if drive_is_available_to_student(drive, student, now=now)),
        None,
    )


def job_is_visible_to_student(student: StudentProfile, job: Job | None, db: Session) -> bool:
    if not job_is_available(job):
        return False
    if job.visibility == "public":
        return True
    if job.visibility != "campus":
        return False
    return available_drive_for_job(student, job, db) is not None
