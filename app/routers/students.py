from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_student
from app.models import Application, ApprovalStatus, DriveStatus, Job, PlacementDrive, ProfileChangeRequest, Resume, StudentProfile, User, UserRole
from app.placement_access import (
    available_drive_for_job,
    available_drives_for_student,
    deadline_has_passed,
    job_is_available,
    job_is_visible_to_student,
)
from app.schemas import ApplicationCreate, ApplicationOut, JobOut, PlacementDriveOut, ResumeOut, StudentProfileCreate, StudentProfileOut
from app.services import application_out, create_notification, drive_out, evaluate_drive_eligibility, evaluate_placement_policies, job_out, student_out
from app.storage import delete_file, file_download_response, save_file, safe_upload_filename, validate_upload_signature

settings = get_settings()
router = APIRouter(prefix="/students", tags=["Students"])


def get_or_create_profile(current_user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        profile = StudentProfile(user_id=current_user.id, organization_id=current_user.organization_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/dashboard")
def dashboard(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    applications = profile.applications
    active = sum(1 for a in applications if a.status.value not in {"rejected", "hired", "withdrawn"})
    scores = [i.overall_score for i in profile.mock_interviews if i.overall_score is not None]
    interviews = len(scores)
    avg_interview = None
    if scores:
        avg_interview = round(sum(scores) / len(scores), 1)
    completion_fields = [profile.full_name, profile.college, profile.degree, profile.branch, profile.graduation_year, profile.cgpa, profile.skills, profile.resume]
    completion = round(sum(bool(x) for x in completion_fields) / len(completion_fields) * 100)
    return {
        "profile_completion": completion,
        "applications": len(applications),
        "active_applications": active,
        "interviews_completed": interviews,
        "average_interview_score": avg_interview,
        "has_resume": profile.resume is not None,
        "verified": profile.is_verified,
    }


@router.get("/profile", response_model=StudentProfileOut)
def get_my_profile(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    return student_out(get_or_create_profile(current_user, db))


@router.put("/profile", response_model=StudentProfileOut)
def update_my_profile(data: StudentProfileCreate, current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    sensitive = {"cgpa", "branch", "graduation_year", "degree", "tenth_percentage", "twelfth_percentage", "diploma_percentage", "active_backlogs", "historical_backlogs", "academic_gap_months"}
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "skills":
            profile.skills = [x.strip() for x in (value or []) if x.strip()][:50]
        elif field == "desired_roles":
            profile.desired_roles = [x.strip() for x in (value or []) if x.strip()][:20]
        elif field == "certifications":
            profile.certifications = [x.strip() for x in (value or []) if x.strip()][:50]
        elif field in sensitive and profile.organization_id and getattr(profile, field, None) != value:
            existing = db.query(ProfileChangeRequest).filter(ProfileChangeRequest.student_id == profile.id, ProfileChangeRequest.field_name == field, ProfileChangeRequest.status == "pending").first()
            if existing:
                existing.new_value = "" if value is None else str(value)
            else:
                db.add(ProfileChangeRequest(student_id=profile.id, organization_id=profile.organization_id, field_name=field, old_value="" if getattr(profile, field, None) is None else str(getattr(profile, field)), new_value="" if value is None else str(value)))
            admins = db.query(User).filter(User.organization_id == profile.organization_id, User.role == UserRole.institution_admin).all()
            for admin in admins:
                create_notification(db, admin.id, "Student profile change awaiting approval", f"{profile.full_name or current_user.username} requested a change to {field.replace('_',' ')}.", organization_id=profile.organization_id, category="profile", priority="normal", link="approvals")
        else:
            setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return student_out(profile)


@router.post("/resume", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    filename = safe_upload_filename(file.filename, "resume.pdf")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    data = await file.read(settings.max_resume_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_resume_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Resume must be {settings.max_resume_mb} MB or smaller")
    validate_upload_signature(data, ".pdf")

    profile = get_or_create_profile(current_user, db)
    existing = db.query(Resume).filter(Resume.student_id == profile.id).first()
    if existing:
        delete_file(db, existing.filepath)
        db.delete(existing)
        db.flush()

    stored_name = f"{profile.id}_{uuid.uuid4().hex[:12]}.pdf"
    filepath = settings.upload_dir / stored_name
    reference = save_file(
        db, category="resume", original_filename=filename, mime_type="application/pdf", data=data, local_path=filepath
    )
    resume = Resume(student_id=profile.id, original_filename=filename, filepath=reference, is_parsed=False)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("/resume", response_model=ResumeOut)
def get_my_resume(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    if not profile.resume:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")
    out = ResumeOut.model_validate(profile.resume)
    out.ai_parsed_data = profile.resume.ai_parsed_data
    return out


@router.get("/resume/download")
def download_my_resume(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    if not profile.resume:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return file_download_response(db, profile.resume.filepath, media_type="application/pdf", filename=profile.resume.original_filename)


def _visible_jobs_for(profile: StudentProfile, db: Session) -> list[Job]:
    jobs = db.query(Job).filter(Job.is_active.is_(True), Job.approval_status == ApprovalStatus.approved).all()
    return [job for job in jobs if job_is_visible_to_student(profile, job, db)]


@router.get("/jobs", response_model=List[JobOut])
def browse_jobs(search: Optional[str] = Query(None), skills: Optional[str] = Query(None), job_type: Optional[str] = Query(None), current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    jobs = _visible_jobs_for(profile, db)
    if search:
        term = search.strip().lower()
        jobs = [j for j in jobs if term in " ".join([
            j.title or "", j.description or "", j.location or "", j.job_type or "",
            j.salary_range or "", j.experience_required or "",
            j.recruiter.company_name if j.recruiter else "",
            " ".join(j.required_skills or []), " ".join(j.preferred_roles or []),
        ]).lower()]
    if job_type and job_type.lower() != "all":
        jobs = [j for j in jobs if job_type.lower() in (j.job_type or "").lower()]
    if skills:
        requested = {s.strip().lower() for s in skills.split(",") if s.strip()}
        jobs = [j for j in jobs if requested.intersection({s.lower() for s in j.required_skills})]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [job_out(j) for j in jobs]


@router.get("/drives", response_model=List[PlacementDriveOut])
def my_placement_drives(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    return [drive_out(drive, db) for drive in available_drives_for_student(profile, db)]


@router.get("/drives/{drive_id}/eligibility")
def drive_eligibility(drive_id: str, current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    if not profile.is_verified:
        raise HTTPException(status_code=403, detail="Institution verification is required for campus placement drives")
    drive = db.query(PlacementDrive).filter(
        PlacementDrive.id == drive_id,
        PlacementDrive.organization_id == profile.organization_id,
        PlacementDrive.status == DriveStatus.open,
    ).first()
    if not drive or not drive.job or drive.job.visibility != "campus" or drive.job.target_organization_id != profile.organization_id:
        raise HTTPException(status_code=404, detail="Placement drive not found")

    result = evaluate_drive_eligibility(profile, drive, db)
    reasons: list[tuple[str, str, str]] = []
    if not job_is_available(drive.job):
        reasons.append(("job_availability", "Job availability", "The campus job is closed, expired, inactive, or awaiting approval"))
    if deadline_has_passed(drive.registration_deadline):
        reasons.append(("registration_deadline", "Registration deadline", "Registration deadline has passed"))

    for key, label, reason in reasons:
        result["eligible"] = False
        result["checks"].append({
            "key": key,
            "label": label,
            "passed": False,
            "actual": datetime.now(timezone.utc).isoformat(),
            "required": drive.registration_deadline.isoformat() if key == "registration_deadline" and drive.registration_deadline else None,
            "reason": reason,
        })
        if reason not in result["reasons"]:
            result["reasons"].append(reason)
    if reasons:
        result["summary"] = "Not eligible because: " + "; ".join(result["reasons"])
    return result


@router.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def apply_to_job(job_id: str, data: ApplicationCreate, current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    job = db.query(Job).filter(Job.id == job_id, Job.is_active.is_(True), Job.approval_status == ApprovalStatus.approved).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or no longer available")
    if deadline_has_passed(job.deadline):
        raise HTTPException(status_code=400, detail="Application deadline has passed")
    if job.visibility == "campus" and not profile.is_verified:
        raise HTTPException(status_code=403, detail="Institution verification is required before applying to campus opportunities")
    if not job_is_visible_to_student(profile, job, db):
        raise HTTPException(status_code=404, detail="Job not found or no longer available")

    drive = available_drive_for_job(profile, job, db) if job.visibility == "campus" else None
    if job.visibility == "campus":
        if not drive:
            raise HTTPException(status_code=403, detail="This campus opportunity is not currently available to your institution")
        eligibility = evaluate_drive_eligibility(profile, drive, db)
        if not eligibility["eligible"]:
            raise HTTPException(status_code=403, detail=eligibility["summary"])
    policy = evaluate_placement_policies(profile, job, db)
    if not policy["allowed"]:
        raise HTTPException(status_code=403, detail="; ".join(policy["reasons"]))
    existing = db.query(Application).filter(Application.student_id == profile.id, Application.job_id == job_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already applied to this job")
    application = Application(student_id=profile.id, job_id=job_id, drive_id=drive.id if drive else None, pipeline_stage_key="registration", cover_note=data.cover_note)
    db.add(application)
    create_notification(db, current_user.id, "Application submitted", f"Your application for {job.title} was submitted successfully.", organization_id=profile.organization_id, category="application", link="applications")
    if job.recruiter and job.recruiter.user_id:
        create_notification(db, job.recruiter.user_id, "New candidate application", f"{profile.full_name or current_user.username} applied for {job.title}.", organization_id=profile.organization_id, category="applicants", link="jobs")
    if profile.organization_id:
        for admin in db.query(User).filter(User.organization_id == profile.organization_id, User.role == UserRole.institution_admin).all():
            create_notification(db, admin.id, "Campus application submitted", f"{profile.full_name or current_user.username} applied for {job.title}.", organization_id=profile.organization_id, category="application", link="applications")
    db.commit()
    db.refresh(application)
    return application_out(application)


@router.get("/applications", response_model=List[ApplicationOut])
def my_applications(current_user: User = Depends(require_student), db: Session = Depends(get_db)):
    profile = get_or_create_profile(current_user, db)
    apps = sorted(profile.applications, key=lambda a: a.applied_at, reverse=True)
    return [application_out(a) for a in apps]
