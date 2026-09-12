from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ApprovalStatus, Job, RecruiterProfile, StudentProfile, User, UserRole
from app.placement_access import job_is_visible_to_student
from app.schemas import JobOut
from app.services import job_out

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _student_profile(current_user: User, db: Session) -> StudentProfile | None:
    return db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()


def _recruiter_profile(current_user: User, db: Session) -> RecruiterProfile | None:
    return db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()


@router.get("", response_model=List[JobOut])
def list_jobs(
    search: Optional[str] = Query(None, max_length=200),
    job_type: Optional[str] = Query(None, max_length=60),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Job).filter(
        Job.is_active.is_(True),
        Job.approval_status == ApprovalStatus.approved,
    )
    if current_user.role == UserRole.student:
        profile = _student_profile(current_user, db)
        if not profile:
            return []
        jobs = query.order_by(Job.created_at.desc()).limit(500).all()
        jobs = [job for job in jobs if job_is_visible_to_student(profile, job, db)]
        if search:
            term = search.strip().lower()
            jobs = [
                job for job in jobs
                if term in " ".join([
                    job.title or "",
                    job.description or "",
                    job.location or "",
                    job.recruiter.company_name if job.recruiter else "",
                    " ".join(job.required_skills or []),
                ]).lower()
            ]
        if job_type:
            term = job_type.strip().lower()
            jobs = [job for job in jobs if term in (job.job_type or "").lower()]
        return [job_out(job) for job in jobs[:200]]

    if current_user.role == UserRole.institution_admin:
        query = query.filter(
            or_(Job.visibility == "public", Job.target_organization_id == current_user.organization_id)
        )
    elif current_user.role == UserRole.recruiter:
        profile = _recruiter_profile(current_user, db)
        if profile:
            query = query.filter(or_(Job.visibility == "public", Job.recruiter_id == profile.id))
        else:
            query = query.filter(Job.visibility == "public")
    elif current_user.role != UserRole.platform_admin:
        raise HTTPException(status_code=403, detail="Not permitted")

    if search:
        query = query.filter(or_(Job.title.ilike(f"%{search.strip()}%"), Job.description.ilike(f"%{search.strip()}%")))
    if job_type:
        query = query.filter(Job.job_type.ilike(f"%{job_type.strip()}%"))
    return [job_out(job) for job in query.order_by(Job.created_at.desc()).limit(200).all()]


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user.role == UserRole.platform_admin:
        return job_out(job)

    if current_user.role == UserRole.recruiter:
        profile = _recruiter_profile(current_user, db)
        if profile and job.recruiter_id == profile.id:
            return job_out(job)

    if not job.is_active or job.approval_status != ApprovalStatus.approved:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.visibility == "public":
        return job_out(job)
    if current_user.role == UserRole.institution_admin:
        if current_user.organization_id and job.target_organization_id == current_user.organization_id:
            return job_out(job)
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user.role == UserRole.student:
        profile = _student_profile(current_user, db)
        if profile and job_is_visible_to_student(profile, job, db):
            return job_out(job)
        raise HTTPException(status_code=404, detail="Job not found")
    raise HTTPException(status_code=404, detail="Job not found")
