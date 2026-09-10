from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_recruiter
from app.models import Application, ApplicationStatus, ApprovalStatus, Job, Organization, RecruiterProfile, User, UserRole
from app.schemas import ApplicationOut, ApplicationStatusUpdate, JobCreate, JobOut, JobUpdate
from app.services import application_out, create_notification, job_out, record_audit

router = APIRouter(prefix="/jobs", tags=["Jobs"])

_CAMPUS_MATERIAL_FIELDS = {
    "title",
    "description",
    "location",
    "job_type",
    "salary_range",
    "experience_required",
    "required_skills",
    "preferred_roles",
    "deadline",
}


def _profile(current_user: User, db: Session) -> RecruiterProfile:
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()
    if not profile:
        profile = RecruiterProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _require_verified(profile: RecruiterProfile):
    if not profile.is_verified:
        raise HTTPException(status_code=403, detail="Recruiter account is awaiting verification")


def _resolve_active_org(slug: str, db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.slug == slug.lower(), Organization.is_active.is_(True)).first()
    if not org:
        raise HTTPException(status_code=400, detail="Target institution was not found")
    return org


def _normalize_list(values: list[str] | None, limit: int) -> list[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()][:limit]


def _material_job_change(job: Job, update: dict) -> bool:
    for field in _CAMPUS_MATERIAL_FIELDS:
        if field not in update:
            continue
        new_value = update[field]
        if field == "required_skills":
            new_value = _normalize_list(new_value, 50)
            old_value = list(job.required_skills)
        elif field == "preferred_roles":
            new_value = _normalize_list(new_value, 20)
            old_value = list(job.preferred_roles)
        else:
            old_value = getattr(job, field)
        if new_value != old_value:
            return True
    return False


def _notify_campus_reapproval(db: Session, current_user: User, job: Job) -> None:
    if not job.target_organization_id:
        return
    record_audit(
        db,
        current_user,
        "recruiter.campus_job.reapproval_required",
        organization_id=job.target_organization_id,
        entity_type="job",
        entity_id=job.id,
        metadata={"title": job.title, "approval_status": ApprovalStatus.pending.value},
    )
    admins = db.query(User).filter(
        User.organization_id == job.target_organization_id,
        User.role == UserRole.institution_admin,
        User.is_active.is_(True),
    ).all()
    for admin in admins:
        create_notification(
            db,
            admin.id,
            "Campus job changed — reapproval required",
            f"{job.recruiter.company_name or 'A recruiter'} changed {job.title}. Review the updated listing before it returns to students.",
            organization_id=job.target_organization_id,
            category="approval",
            priority="high",
            link="jobs",
        )


@router.get("/my/listings", response_model=List[JobOut])
def my_job_listings(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    jobs = db.query(Job).filter(Job.recruiter_id == profile.id).order_by(Job.created_at.desc()).all()
    return [job_out(j) for j in jobs]


@router.get("", response_model=List[JobOut])
def list_jobs(search: Optional[str] = Query(None), job_type: Optional[str] = Query(None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Job).filter(Job.is_active.is_(True), Job.approval_status == ApprovalStatus.approved)
    if current_user.role == UserRole.student:
        if current_user.organization_id:
            query = query.filter((Job.visibility == "public") | (Job.target_organization_id == current_user.organization_id))
        else:
            query = query.filter(Job.visibility == "public")
    elif current_user.role == UserRole.institution_admin:
        query = query.filter((Job.visibility == "public") | (Job.target_organization_id == current_user.organization_id))
    elif current_user.role == UserRole.recruiter:
        profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()
        if profile:
            query = query.filter((Job.visibility == "public") | (Job.recruiter_id == profile.id))
        else:
            query = query.filter(Job.visibility == "public")
    if search:
        query = query.filter((Job.title.ilike(f"%{search}%")) | (Job.description.ilike(f"%{search}%")))
    if job_type:
        query = query.filter(Job.job_type.ilike(f"%{job_type}%"))
    return [job_out(j) for j in query.order_by(Job.created_at.desc()).limit(200).all()]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if current_user.role == UserRole.platform_admin:
        return job_out(job)

    if current_user.role == UserRole.recruiter:
        profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()
        if profile and job.recruiter_id == profile.id:
            return job_out(job)

    if not job.is_active or job.approval_status != ApprovalStatus.approved:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.visibility == "public":
        return job_out(job)
    if current_user.role in {UserRole.student, UserRole.institution_admin} and current_user.organization_id and job.target_organization_id == current_user.organization_id:
        return job_out(job)
    raise HTTPException(status_code=404, detail="Job not found")


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    _require_verified(profile)
    visibility = data.visibility.lower().strip()
    if visibility not in {"public", "campus"}:
        raise HTTPException(status_code=400, detail="visibility must be public or campus")

    target_slug = (data.target_organization_slug or "").strip() or None
    if visibility != "campus" and target_slug:
        raise HTTPException(status_code=400, detail="Target institution is only valid for campus jobs")

    target_org = None
    if visibility == "campus":
        if not target_slug:
            raise HTTPException(status_code=400, detail="Campus jobs require a target institution code")
        target_org = _resolve_active_org(target_slug, db)

    job = Job(
        recruiter_id=profile.id,
        title=data.title,
        description=data.description,
        location=data.location,
        job_type=data.job_type,
        salary_range=data.salary_range,
        experience_required=data.experience_required,
        deadline=data.deadline,
        visibility=visibility,
        target_organization_id=target_org.id if target_org else None,
        approval_status=ApprovalStatus.pending if visibility == "campus" else ApprovalStatus.approved,
        is_active=visibility != "campus",
    )
    job.required_skills = _normalize_list(data.required_skills, 50)
    job.preferred_roles = _normalize_list(data.preferred_roles, 20)
    db.add(job)
    db.flush()
    if target_org:
        record_audit(db, current_user, "recruiter.campus_job.submitted", organization_id=target_org.id, entity_type="job", entity_id=job.id, metadata={"title": job.title, "company": profile.company_name})
        admins = db.query(User).filter(User.organization_id == target_org.id, User.role == UserRole.institution_admin).all()
        for admin in admins:
            create_notification(db, admin.id, "Campus job awaiting approval", f"{profile.company_name or 'A recruiter'} submitted {job.title} for campus approval.", organization_id=target_org.id, category="approval", priority="high", link="jobs")
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: str, data: JobUpdate, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    _require_verified(profile)
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == profile.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")

    update = data.model_dump(exclude_unset=True)
    target_slug_raw = update.pop("target_organization_slug", None)
    target_slug = str(target_slug_raw).strip() if target_slug_raw is not None else None
    target_slug = target_slug or None

    final_visibility = str(update.get("visibility", job.visibility)).lower().strip()
    if final_visibility not in {"public", "campus"}:
        raise HTTPException(status_code=400, detail="visibility must be public or campus")
    if final_visibility != "campus" and target_slug:
        raise HTTPException(status_code=400, detail="Target institution is only valid for campus jobs")

    visibility_changed = final_visibility != job.visibility
    target_org = job.target_institution
    target_changed = False
    if final_visibility == "campus":
        slug = target_slug or (job.target_institution.slug if job.target_institution else None)
        if not slug:
            raise HTTPException(status_code=400, detail="Campus jobs require a target institution code")
        target_org = _resolve_active_org(slug, db)
        target_changed = job.target_organization_id != target_org.id
    else:
        target_changed = job.target_organization_id is not None
        target_org = None

    material_changed = visibility_changed or target_changed or _material_job_change(job, update)

    if "required_skills" in update:
        update["required_skills"] = _normalize_list(update["required_skills"], 50)
    if "preferred_roles" in update:
        update["preferred_roles"] = _normalize_list(update["preferred_roles"], 20)

    requested_active = update.pop("is_active", None) if "is_active" in update else None
    update.pop("visibility", None)

    for field, value in update.items():
        if field == "required_skills":
            job.required_skills = value
        elif field == "preferred_roles":
            job.preferred_roles = value
        else:
            setattr(job, field, value)

    job.visibility = final_visibility
    job.target_organization_id = target_org.id if target_org else None

    if final_visibility == "campus":
        if material_changed:
            job.approval_status = ApprovalStatus.pending
            job.is_active = False
            _notify_campus_reapproval(db, current_user, job)
        elif job.approval_status != ApprovalStatus.approved:
            job.is_active = False
        elif requested_active is not None:
            job.is_active = bool(requested_active)
    else:
        job.approval_status = ApprovalStatus.approved
        if visibility_changed:
            job.is_active = True if requested_active is None else bool(requested_active)
        elif requested_active is not None:
            job.is_active = bool(requested_active)

    if job.target_organization_id:
        record_audit(db, current_user, "recruiter.campus_job.updated", organization_id=job.target_organization_id, entity_type="job", entity_id=job.id, metadata={"title": job.title, "approval_status": job.approval_status.value, "material_change": material_changed})
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == profile.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
    if job.target_organization_id:
        record_audit(db, current_user, "recruiter.campus_job.deleted", organization_id=job.target_organization_id, entity_type="job", entity_id=job.id, metadata={"title": job.title})
    db.delete(job)
    db.commit()


@router.get("/{job_id}/applicants", response_model=List[ApplicationOut])
def list_applicants(job_id: str, status_filter: Optional[str] = Query(None), current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == profile.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
    apps = list(job.applications)
    if status_filter:
        apps = [a for a in apps if a.status.value == status_filter]
    apps.sort(key=lambda a: (a.ai_match_score or 0, a.applied_at), reverse=True)
    return [application_out(a) for a in apps]


@router.patch("/{job_id}/applicants/{application_id}/status", response_model=ApplicationOut)
def update_application_status(job_id: str, application_id: str, data: ApplicationStatusUpdate, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == profile.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")
    application = db.query(Application).filter(Application.id == application_id, Application.job_id == job_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    application.status = ApplicationStatus(data.status.value)
    stage_map = {"applied": "registration", "shortlisted": "eligibility-screening", "interview": "technical-round-1", "offered": "offer", "hired": "joined", "rejected": "rejected", "withdrawn": "withdrawn"}
    application.pipeline_stage_key = stage_map.get(data.status.value, application.pipeline_stage_key)
    if data.recruiter_notes is not None:
        application.recruiter_notes = data.recruiter_notes
    if application.student and application.student.user_id:
        create_notification(db, application.student.user_id, "Application status updated", f"Your {job.title} application is now {data.status.value.replace('_',' ')}.", organization_id=application.student.organization_id, category="application", priority="high" if data.status.value in {"interview","offered","hired"} else "normal", link="applications")
    if job.target_organization_id:
        record_audit(db, current_user, "recruiter.application.status_changed", organization_id=job.target_organization_id, entity_type="application", entity_id=application.id, metadata={"job_id": job.id, "status": application.status.value})
    db.commit()
    db.refresh(application)
    return application_out(application)
