from __future__ import annotations

import json
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_recruiter
from app.models import Application, Job, RecruiterProfile, StudentProfile, User
from app.schemas import CompanyTrustAssessment, MockInterviewDetailOut, RecruiterAnalyticsOut, RecruiterProfileCreate, RecruiterProfileOut, SkillDistribution, StudentProfileOut
from app.services import company_trust_assessment, student_out
from app.storage import file_download_response

settings = get_settings()
router = APIRouter(prefix="/recruiters", tags=["Recruiters"])


def _profile(current_user: User, db: Session) -> RecruiterProfile:
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()
    if not profile:
        profile = RecruiterProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _candidate_ids(profile: RecruiterProfile, db: Session) -> set[str]:
    rows = db.query(Application.student_id).join(Job, Application.job_id == Job.id).filter(Job.recruiter_id == profile.id).all()
    return {row[0] for row in rows}


def _can_access_student(profile: RecruiterProfile, student: StudentProfile, db: Session) -> bool:
    if not student.placement_opt_in:
        return False
    if settings.allow_talent_pool_search:
        return True
    return student.id in _candidate_ids(profile, db)


@router.get("/dashboard")
def dashboard(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    jobs = profile.jobs
    apps = [a for j in jobs for a in j.applications]
    return {
        "verified": profile.is_verified,
        "active_jobs": sum(1 for j in jobs if j.is_active),
        "applications": len(apps),
        "shortlisted": sum(1 for a in apps if a.status.value == "shortlisted"),
        "interviews": sum(1 for a in apps if a.status.value == "interview"),
        "offers": sum(1 for a in apps if a.status.value == "offered"),
        "hired": sum(1 for a in apps if a.status.value == "hired"),
    }


@router.get("/profile", response_model=RecruiterProfileOut)
def get_recruiter_profile(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    return _profile(current_user, db)


@router.put("/profile", response_model=RecruiterProfileOut)
def update_recruiter_profile(data: RecruiterProfileCreate, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    jobs = list(profile.jobs)
    if jobs:
        complete = sum(1 for j in jobs if all([j.title, j.description, j.location, j.job_type, j.required_skills]))
        profile.job_consistency_score = round(complete / len(jobs) * 100, 1)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/company-trust", response_model=CompanyTrustAssessment)
def company_trust(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Return an evidence-based company trust review for the signed-in recruiter."""
    return company_trust_assessment(_profile(current_user, db), db)


@router.get("/students/search", response_model=List[StudentProfileOut])
def search_students(skills: Optional[str] = Query(None), min_cgpa: Optional[float] = Query(None), college: Optional[str] = Query(None), graduation_year: Optional[int] = Query(None), limit: int = Query(50, ge=1, le=100), current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    if not profile.is_verified:
        raise HTTPException(status_code=403, detail="Recruiter account is awaiting verification")
    query = db.query(StudentProfile).filter(StudentProfile.placement_opt_in.is_(True))
    if not settings.allow_talent_pool_search:
        ids = _candidate_ids(profile, db)
        if not ids:
            return []
        query = query.filter(StudentProfile.id.in_(ids))
    if min_cgpa is not None:
        query = query.filter(StudentProfile.cgpa >= min_cgpa)
    if college:
        query = query.filter(StudentProfile.college.ilike(f"%{college}%"))
    if graduation_year:
        query = query.filter(StudentProfile.graduation_year == graduation_year)
    students = query.order_by(StudentProfile.updated_at.desc()).limit(300).all()
    if skills:
        wanted = {s.strip().lower() for s in skills.split(",") if s.strip()}
        students = [s for s in students if wanted.intersection({x.lower() for x in s.skills})]
    return [student_out(s) for s in students[:limit]]


@router.get("/students/{student_id}", response_model=StudentProfileOut)
def get_student(student_id: str, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if not student or not _can_access_student(profile, student, db):
        raise HTTPException(status_code=404, detail="Candidate not found or not available in your pipeline")
    return student_out(student)


@router.get("/students/{student_id}/resume")
def download_student_resume(student_id: str, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if not student or not _can_access_student(profile, student, db) or not student.resume:
        raise HTTPException(status_code=404, detail="Resume not available")
    return file_download_response(db, student.resume.filepath, media_type="application/pdf", filename=student.resume.original_filename)


@router.get("/analytics", response_model=RecruiterAnalyticsOut)
def analytics(current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    applications = [a for j in profile.jobs for a in j.applications]
    cgpas = [a.student.cgpa for a in applications if a.student and a.student.cgpa is not None]
    skills = Counter()
    for app in applications:
        if app.student:
            skills.update(app.student.skills)
    return RecruiterAnalyticsOut(
        total_jobs=len(profile.jobs),
        total_applications=len(applications),
        average_cgpa=round(sum(cgpas) / len(cgpas), 2) if cgpas else None,
        top_skills=[SkillDistribution(skill=k, count=v) for k, v in skills.most_common(10)],
    )


@router.get("/students/{student_id}/interviews", response_model=List[MockInterviewDetailOut])
def student_interviews(student_id: str, current_user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    profile = _profile(current_user, db)
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if not student or not _can_access_student(profile, student, db):
        raise HTTPException(status_code=404, detail="Candidate not found or not available in your pipeline")
    results = []
    for iv in sorted(student.mock_interviews, key=lambda x: x.created_at, reverse=True):
        results.append(MockInterviewDetailOut(
            id=iv.id,
            job_id=iv.job_id,
            job_title=iv.job.title if iv.job else "Unknown role",
            company_name=iv.job.recruiter.company_name if iv.job and iv.job.recruiter else None,
            questions=json.loads(iv.questions_json or "[]"),
            answers=json.loads(iv.answers_json or "[]"),
            evaluations=json.loads(iv.evaluation_json or "[]"),
            overall_score=iv.overall_score,
            overall_feedback=iv.overall_feedback,
            created_at=iv.created_at,
        ))
    return results
