from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import (
    ApprovalStatus,
    DriveStatus,
    Job,
    Organization,
    OrganizationType,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
    utcnow,
)
from app.utils import get_hashed_password


def seed_preview_data(db: Session) -> None:
    """Create disposable staging data only when explicitly enabled outside production."""
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    enabled = os.getenv("PREVIEW_SEED", "false").strip().lower() == "true"
    if not enabled or environment == "production":
        return

    tpo_password = os.getenv("PREVIEW_TPO_PASSWORD", "").strip()
    student_password = os.getenv("PREVIEW_STUDENT_PASSWORD", "").strip()
    recruiter_password = os.getenv("PREVIEW_RECRUITER_PASSWORD", "").strip()
    if not all((tpo_password, student_password, recruiter_password)):
        return

    org = db.query(Organization).filter(Organization.slug == "placeai-preview").first()
    if not org:
        org = Organization(
            name="PlaceAI Preview Institute",
            slug="placeai-preview",
            organization_type=OrganizationType.institution,
            city="Pune",
            state="Maharashtra",
            country="India",
            is_active=True,
        )
        db.add(org)
        db.flush()

    def ensure_user(email: str, username: str, role: UserRole, password: str, org_id: str | None = None) -> User:
        row = db.query(User).filter(User.email == email).first()
        if row:
            # Preview accounts are disposable. Re-apply the configured credentials on
            # every preview startup so Render env changes cannot leave stale hashes.
            row.username = username
            row.hashed_password = get_hashed_password(password)
            row.role = role
            row.organization_id = org_id
            row.email_verified = True
            row.is_active = True
            db.flush()
            return row
        row = User(
            email=email,
            username=username,
            hashed_password=get_hashed_password(password),
            role=role,
            organization_id=org_id,
            email_verified=True,
            is_active=True,
        )
        db.add(row)
        db.flush()
        return row

    tpo = ensure_user(
        "preview-tpo@placeai.example.com",
        "preview_tpo",
        UserRole.institution_admin,
        tpo_password,
        org.id,
    )
    recruiter_user = ensure_user(
        "preview-recruiter@placeai.example.com",
        "preview_recruiter",
        UserRole.recruiter,
        recruiter_password,
    )
    student_user = ensure_user(
        "preview-student@placeai.example.com",
        "preview_student",
        UserRole.student,
        student_password,
        org.id,
    )
    pending_user = ensure_user(
        "preview-pending@placeai.example.com",
        "preview_pending",
        UserRole.student,
        student_password,
        org.id,
    )

    recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == recruiter_user.id).first()
    if not recruiter:
        recruiter = RecruiterProfile(
            user_id=recruiter_user.id,
            full_name="Preview Recruiter",
            company_name="Northstar Technologies",
            company_website="https://example.com",
            industry="Technology",
            designation="Campus Hiring Lead",
            official_email_domain="example.com",
            provisioned_by_organization_id=org.id,
            is_verified=True,
            company_verification_status="verified",
            company_verification_confidence=85,
            previous_successful_placements=24,
        )
        db.add(recruiter)
        db.flush()

    student = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
    if not student:
        student = StudentProfile(
            user_id=student_user.id,
            organization_id=org.id,
            full_name="Aarav Preview",
            college=org.name,
            degree="B.Tech",
            branch="Computer Science",
            graduation_year=2027,
            cgpa=8.4,
            phone="9000000001",
            linkedin_url="https://www.linkedin.com/in/preview-student",
            is_verified=True,
            placement_opt_in=True,
        )
        student.skills = ["Python", "SQL", "FastAPI"]
        student.desired_roles = ["Backend Developer", "Software Engineer"]
        student.certifications = ["Python Foundations"]
        db.add(student)
        db.flush()

    pending = db.query(StudentProfile).filter(StudentProfile.user_id == pending_user.id).first()
    if not pending:
        pending = StudentProfile(
            user_id=pending_user.id,
            organization_id=org.id,
            full_name="Meera Preview",
            college=org.name,
            degree="B.Tech",
            branch="Computer Science",
            graduation_year=2027,
            cgpa=8.1,
            is_verified=False,
            placement_opt_in=True,
        )
        pending.skills = ["Python", "SQL"]
        pending.desired_roles = ["Software Engineer"]
        db.add(pending)
        db.flush()

    job = db.query(Job).filter(
        Job.recruiter_id == recruiter.id,
        Job.title == "Graduate Backend Engineer",
        Job.target_organization_id == org.id,
    ).first()
    if not job:
        job = Job(
            recruiter_id=recruiter.id,
            title="Graduate Backend Engineer",
            description="Build and maintain backend APIs, data workflows and production services.",
            location="Pune / Hybrid",
            job_type="Full-time",
            salary_range="₹8–10 LPA",
            experience_required="Fresher",
            approval_status=ApprovalStatus.approved,
            visibility="campus",
            target_organization_id=org.id,
            is_active=True,
            deadline=utcnow() + timedelta(days=5),
        )
        job.required_skills = ["Python", "SQL"]
        job.preferred_roles = ["Backend Developer"]
        db.add(job)
        db.flush()

    drive = db.query(PlacementDrive).filter(
        PlacementDrive.organization_id == org.id,
        PlacementDrive.job_id == job.id,
        PlacementDrive.title == "Northstar Graduate Hiring 2027",
    ).first()
    if not drive:
        drive = PlacementDrive(
            organization_id=org.id,
            job_id=job.id,
            title="Northstar Graduate Hiring 2027",
            status=DriveStatus.open,
            min_cgpa=7.0,
            registration_deadline=utcnow() + timedelta(days=2),
            event_date=utcnow() + timedelta(days=7),
            allow_placed_students=False,
            notes="Preview-only drive used to validate PlaceAI Drive Rescue and student next actions.",
        )
        drive.allowed_graduation_years = [2027]
        drive.allowed_branches = ["Computer Science"]
        drive.required_skills = ["Python", "SQL"]
        db.add(drive)

    db.commit()
