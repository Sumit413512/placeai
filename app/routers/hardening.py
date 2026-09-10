from __future__ import annotations

import json
import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai_rate_limit import recruiter_ai_guard
from app.database import get_db
from app.dependencies import require_institution_admin, require_recruiter
from app.models import (
    Application,
    ApplicationStatus,
    ApprovalStatus,
    DriveStatus,
    Job,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
)
from app.routers.ai import PROMPT_GUARDRAIL, call_gemini, extract_json_from_response, get_gemini_client
from app.routers.institutions import _org
from app.schemas import AIRankResult, AIRankedCandidate, InstitutionDashboardOut, JobApprovalUpdate, JobOut
from app.services import create_notification, job_out, record_audit

router = APIRouter(tags=["Production hardening"])
MAX_AI_REASONING_CHARS = 2000


def _normalize_ai_score(value: object) -> float:
    """Return a finite score in [0, 100], rejecting malformed/non-finite model output."""
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI ranking returned an invalid candidate score.",
        ) from exc
    if not math.isfinite(score):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI ranking returned a non-finite candidate score.",
        )
    return min(100.0, max(0.0, score))


def _bounded_reasoning(value: object) -> str:
    text = "" if value is None else str(value)
    return text.strip()[:MAX_AI_REASONING_CHARS]


@router.get("/institutions/dashboard", response_model=InstitutionDashboardOut)
def hardened_institution_dashboard(
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Scope activity to the institution's students, including their public-job applications."""
    org = _org(current_user, db)
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org.id).all()
    student_ids = [student.id for student in students]

    target_jobs = db.query(Job).filter(Job.target_organization_id == org.id).all()
    applications = (
        db.query(Application).filter(Application.student_id.in_(student_ids)).all()
        if student_ids
        else []
    )

    offered_applications = [
        application
        for application in applications
        if application.status in {ApplicationStatus.offered, ApplicationStatus.hired}
    ]
    hired_student_ids = {
        application.student_id
        for application in applications
        if application.status == ApplicationStatus.hired
    }
    eligible_base = max(len(students), 1)

    return InstitutionDashboardOut(
        organization=org,
        total_students=len(students),
        verified_students=sum(1 for student in students if student.is_verified),
        active_jobs=sum(
            1
            for job in target_jobs
            if job.visibility == "campus"
            and job.is_active
            and job.approval_status == ApprovalStatus.approved
        ),
        open_drives=db.query(PlacementDrive).filter(
            PlacementDrive.organization_id == org.id,
            PlacementDrive.status == DriveStatus.open,
        ).count(),
        total_applications=len(applications),
        offers=len(offered_applications),
        hires=len(hired_student_ids),
        placement_rate=round(len(hired_student_ids) / eligible_base * 100, 1),
    )


@router.patch("/institutions/jobs/{job_id}/approval", response_model=JobOut)
def hardened_approve_job(
    job_id: str,
    data: JobApprovalUpdate,
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    """Approve only a genuine campus-targeted listing for the caller's institution."""
    org = _org(current_user, db)
    job = db.query(Job).filter(Job.id == job_id, Job.target_organization_id == org.id).first()
    if not job or job.visibility != "campus":
        raise HTTPException(status_code=404, detail="Campus job not found")

    job.approval_status = ApprovalStatus(data.approval_status.value)
    job.is_active = data.approval_status.value == ApprovalStatus.approved.value
    record_audit(
        db,
        current_user,
        "institution.job.approval_changed",
        organization_id=org.id,
        entity_type="job",
        entity_id=job.id,
        metadata={"approval_status": data.approval_status.value, "title": job.title},
    )
    if job.recruiter and job.recruiter.user_id:
        create_notification(
            db,
            job.recruiter.user_id,
            f"Campus job {data.approval_status.value}",
            f"{org.name} {data.approval_status.value} your campus job: {job.title}.",
            organization_id=org.id,
            category="campus",
            priority="high" if data.approval_status.value == "approved" else "normal",
            link="jobs",
        )
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.post(
    "/ai/rank-candidates/{job_id}",
    dependencies=[Depends(recruiter_ai_guard)],
    response_model=AIRankResult,
)
def hardened_rank_candidates(
    job_id: str,
    current_user: User = Depends(require_recruiter),
    db: Session = Depends(get_db),
):
    """Rank candidates while validating all model-generated values before persistence."""
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == current_user.id).first()
    if not profile or not profile.is_verified:
        raise HTTPException(status_code=403, detail="Verified recruiter access required")
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == profile.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")

    applications = list(job.applications)
    if not applications:
        raise HTTPException(status_code=404, detail="No applicants for this job yet")

    candidate_info = []
    for application in applications:
        student = application.student
        candidate_info.append(
            {
                "application_id": application.id,
                "student_id": student.id,
                "name": student.full_name or "Unknown",
                "email": student.user.email if student.user else "",
                "college": student.college or "N/A",
                "degree": student.degree or "N/A",
                "cgpa": student.cgpa or "N/A",
                "graduation_year": student.graduation_year or "N/A",
                "skills": student.skills,
                "desired_roles": student.desired_roles,
                "resume_summary": (
                    (student.resume.ai_parsed_data or {}).get("summary", "No AI summary available")
                    if student.resume
                    else "No resume"
                ),
                "cover_note": application.cover_note or "None provided",
            }
        )

    prompt = f"""
{PROMPT_GUARDRAIL}

You are an expert technical recruiter AI. Rank the following candidates for the job below.
Return ONLY a valid JSON array (no other text) where each element is:
{{
  "application_id": "...",
  "score": <number 0-100>,
  "reasoning": "2-3 sentence explanation of fit"
}}
Sort by score descending.

Job Title: {job.title}
Job Description: {job.description}
Required Skills: {json.dumps(job.required_skills)}
Preferred Roles: {json.dumps(job.preferred_roles)}
Experience Required: {job.experience_required or 'Not specified'}

Candidates:
{json.dumps(candidate_info, indent=2)}
"""

    raw = call_gemini(get_gemini_client(), prompt)
    rankings_raw = extract_json_from_response(raw)
    if not isinstance(rankings_raw, list):
        if not isinstance(rankings_raw, dict):
            raise HTTPException(status_code=502, detail="AI ranking returned an invalid payload.")
        rankings_raw = rankings_raw.get("rankings", rankings_raw.get("candidates", []))
    if not isinstance(rankings_raw, list):
        raise HTTPException(status_code=502, detail="AI ranking returned an invalid payload.")

    app_map = {application.id: application for application in applications}
    normalized: list[tuple[str, float, str]] = []
    seen: set[str] = set()
    for row in rankings_raw:
        if not isinstance(row, dict):
            raise HTTPException(status_code=502, detail="AI ranking returned an invalid candidate row.")
        app_id = str(row.get("application_id") or "")
        if app_id not in app_map or app_id in seen:
            continue
        seen.add(app_id)
        normalized.append(
            (
                app_id,
                _normalize_ai_score(row.get("score")),
                _bounded_reasoning(row.get("reasoning")),
            )
        )

    ranked_candidates = []
    for app_id, score, reasoning in normalized:
        application = app_map[app_id]
        application.ai_match_score = score
        application.ai_match_reasoning = reasoning
        student = application.student
        ranked_candidates.append(
            AIRankedCandidate(
                student_id=student.id,
                full_name=student.full_name,
                email=student.user.email if student.user else "",
                college=student.college,
                cgpa=student.cgpa,
                skills=student.skills,
                ai_match_score=score,
                ai_match_reasoning=reasoning,
            )
        )

    db.commit()
    return AIRankResult(
        job_id=job.id,
        job_title=job.title,
        ranked_candidates=ranked_candidates,
    )
