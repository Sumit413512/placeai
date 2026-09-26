from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Application,
    ApprovalStatus,
    DriveStatus,
    InterviewSchedule,
    MockInterview,
    PlacementAction,
    PlacementDrive,
    StudentProfile,
)
from app.services import evaluate_drive_eligibility, placement_readiness


SYSTEM_ACTION_TYPES = {
    "profile_incomplete",
    "resume_missing",
    "verification_blocker",
    "eligible_not_applied",
    "drive_requirement_blocker",
    "interview_prep_due",
}
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "normal": 3, "low": 4}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _due_priority(due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return "medium"
    remaining = due_at - now
    if remaining <= timedelta(hours=24):
        return "high"
    if remaining <= timedelta(hours=72):
        return "medium"
    return "normal"


def _component_map(payload: dict) -> dict[str, int]:
    return {str(item.get("name")): int(item.get("score") or 0) for item in payload.get("components", [])}


def readiness_evidence(student: StudentProfile, db: Session) -> dict:
    """Return explainable readiness evidence without presenting an employment prediction."""
    base = placement_readiness(student, db)
    components = _component_map(base)
    mocks = (
        db.query(MockInterview)
        .filter(MockInterview.student_id == student.id, MockInterview.overall_score.is_not(None))
        .order_by(MockInterview.created_at.desc())
        .limit(10)
        .all()
    )
    scores = [int(row.overall_score or 0) for row in mocks]
    latest_mock = mocks[0] if mocks else None
    resume = student.resume
    parsed = resume.ai_parsed_data if resume else None
    parsed_experience = parsed.get("experience") if isinstance(parsed, dict) else []
    parsed_experience = parsed_experience if isinstance(parsed_experience, list) else []
    profile_fields = {
        "full_name": student.full_name,
        "degree": student.degree,
        "branch": student.branch,
        "graduation_year": student.graduation_year,
        "cgpa": student.cgpa,
        "phone": student.phone,
        "linkedin_url": student.linkedin_url,
    }
    present_profile_fields = [key for key, value in profile_fields.items() if value not in (None, "")]
    evidence = [
        {
            "key": "profile",
            "label": "Profile completeness",
            "score": components.get("Profile completeness", 0),
            "confidence": "high" if student.is_verified else "medium",
            "source": "Student profile + institution verification",
            "evidence": f"{len(present_profile_fields)}/{len(profile_fields)} core fields present; institution verification {'complete' if student.is_verified else 'pending'}.",
            "observed_at": _iso(student.updated_at),
        },
        {
            "key": "resume",
            "label": "Resume strength",
            "score": components.get("Resume strength", 0),
            "confidence": "high" if resume and resume.is_parsed else ("medium" if resume else "low"),
            "source": "Uploaded resume" + (" + parsed structure" if resume and resume.is_parsed else ""),
            "evidence": "Resume uploaded and parsed for structured evidence." if resume and resume.is_parsed else ("Resume uploaded; structured parsing has not been completed." if resume else "No resume evidence is currently available."),
            "observed_at": _iso(resume.uploaded_at if resume else None),
        },
        {
            "key": "technical",
            "label": "Technical skills",
            "score": components.get("Technical skills", 0),
            "confidence": "medium" if student.skills or student.certifications else "low",
            "source": "Profile skills and certifications",
            "evidence": f"{len(student.skills)} skill(s) and {len(student.certifications)} certification(s) recorded. Profile claims should be strengthened with assessments and project evidence.",
            "observed_at": _iso(student.updated_at),
        },
        {
            "key": "role_alignment",
            "label": "Role alignment",
            "score": components.get("Role alignment", 0),
            "confidence": "medium" if student.desired_roles else "low",
            "source": "Target-role preferences",
            "evidence": f"{len(student.desired_roles)} target role(s) recorded: {', '.join(student.desired_roles[:4]) or 'none yet'}.",
            "observed_at": _iso(student.updated_at),
        },
        {
            "key": "interview",
            "label": "Interview readiness",
            "score": components.get("Interview readiness", 0),
            "confidence": "high" if len(scores) >= 3 else ("medium" if scores else "low"),
            "source": "Scored mock-interview attempts",
            "evidence": (f"{len(scores)} scored attempt(s); latest {scores[0]}/100; recent average {round(sum(scores) / len(scores))}/100." if scores else "No scored mock-interview evidence is available yet."),
            "observed_at": _iso(latest_mock.created_at if latest_mock else None),
        },
        {
            "key": "academic",
            "label": "Academic eligibility",
            "score": components.get("Academic eligibility", 0),
            "confidence": "high" if student.is_verified else "medium",
            "source": "Academic profile" + (" verified by institution" if student.is_verified else ""),
            "evidence": f"CGPA {student.cgpa if student.cgpa is not None else 'not recorded'}; active backlogs {student.active_backlogs or 0}; academic gap {student.academic_gap_months or 0} month(s).",
            "observed_at": _iso(student.updated_at),
        },
        {
            "key": "projects",
            "label": "Project evidence",
            "score": components.get("Project evidence", 0),
            "confidence": "medium" if parsed_experience else "low",
            "source": "Resume project/experience evidence",
            "evidence": f"{len(parsed_experience)} parsed project/experience item(s) available." if parsed_experience else "No structured project/experience evidence is available yet.",
            "observed_at": _iso(resume.uploaded_at if resume else None),
        },
    ]
    if base["score"] >= 85:
        band = "Strong evidence"
    elif base["score"] >= 70:
        band = "Building readiness"
    elif base["score"] >= 50:
        band = "Developing"
    else:
        band = "Foundation"
    first_action = (base.get("recommended_actions") or ["Review your next eligible opportunity."])[0]
    lower = first_action.lower()
    view = "profile"
    if "resume" in lower or "project" in lower:
        view = "resume"
    elif "interview" in lower:
        view = "mock-interview"
    elif "opportun" in lower or "drive" in lower:
        view = "opportunities"
    high_confidence = sum(1 for item in evidence if item["confidence"] == "high")
    return {
        **base,
        "readiness_band": band,
        "evidence": evidence,
        "evidence_summary": {
            "high_confidence_sources": high_confidence,
            "total_sources": len(evidence),
            "last_updated_at": _iso(student.updated_at),
        },
        "next_best_action": {
            "title": first_action,
            "view": view,
            "reason": "Selected from the lowest-confidence or lowest-scoring evidence currently available.",
        },
    }


def _application_for(student_id: str, drive: PlacementDrive, db: Session) -> Application | None:
    return (
        db.query(Application)
        .filter(
            Application.student_id == student_id,
            Application.job_id == drive.job_id,
        )
        .first()
    )


def _upsert_action(
    db: Session,
    *,
    organization_id: str,
    source_key: str,
    action_type: str,
    title: str,
    description: str,
    priority: str,
    student_id: str | None = None,
    drive_id: str | None = None,
    job_id: str | None = None,
    due_at: datetime | None = None,
    details: dict | None = None,
) -> tuple[PlacementAction, bool]:
    row = (
        db.query(PlacementAction)
        .filter(
            PlacementAction.organization_id == organization_id,
            PlacementAction.source_key == source_key,
        )
        .first()
    )
    created = row is None
    if row is None:
        row = PlacementAction(
            organization_id=organization_id,
            source_key=source_key,
            action_type=action_type,
            title=title,
            description=description,
            priority=priority,
            student_id=student_id,
            drive_id=drive_id,
            job_id=job_id,
            due_at=due_at,
        )
        row.details = details or {}
        db.add(row)
    elif row.status in {"open", "in_progress"}:
        row.title = title
        row.description = description
        row.priority = priority
        row.student_id = student_id
        row.drive_id = drive_id
        row.job_id = job_id
        row.due_at = due_at
        row.details = details or {}
    return row, created


def sync_placement_actions(organization_id: str, db: Session) -> dict:
    """Materialize objective placement exceptions into a human-controlled action queue."""
    now = utcnow()
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == organization_id).all()
    drives = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.organization_id == organization_id,
            PlacementDrive.status == DriveStatus.open,
        )
        .all()
    )
    active_keys: set[str] = set()
    created = 0
    updated = 0

    for student in students:
        missing = [
            label
            for label, value in (
                ("full name", student.full_name),
                ("branch", student.branch),
                ("graduation year", student.graduation_year),
                ("CGPA", student.cgpa),
                ("phone", student.phone),
            )
            if value in (None, "")
        ]
        if missing:
            key = f"profile:{student.id}"
            active_keys.add(key)
            _, was_created = _upsert_action(
                db,
                organization_id=organization_id,
                source_key=key,
                action_type="profile_incomplete",
                title=f"Complete {student.full_name or 'student'} placement profile",
                description=f"Missing placement fields: {', '.join(missing)}.",
                priority="medium",
                student_id=student.id,
                details={"missing_fields": missing},
            )
            created += int(was_created)
            updated += int(not was_created)
        if student.resume is None:
            key = f"resume:{student.id}"
            active_keys.add(key)
            _, was_created = _upsert_action(
                db,
                organization_id=organization_id,
                source_key=key,
                action_type="resume_missing",
                title=f"Resume missing for {student.full_name or 'student'}",
                description="A current resume is required before meaningful role preparation and recruiter review.",
                priority="medium",
                student_id=student.id,
            )
            created += int(was_created)
            updated += int(not was_created)

    for drive in drives:
        deadline = drive.registration_deadline
        if deadline is not None and deadline <= now:
            continue
        job = drive.job
        if job is None or not job.is_active or _enum_value(job.approval_status) != ApprovalStatus.approved.value:
            continue
        for student in students:
            if not student.placement_opt_in:
                continue
            eligibility = evaluate_drive_eligibility(student, drive, db)
            application = _application_for(student.id, drive, db)
            if eligibility["eligible"] and application is None:
                if not student.is_verified:
                    key = f"drive:{drive.id}:verification:{student.id}"
                    active_keys.add(key)
                    _, was_created = _upsert_action(
                        db,
                        organization_id=organization_id,
                        source_key=key,
                        action_type="verification_blocker",
                        title=f"Verify {student.full_name or 'student'} before {drive.title}",
                        description="The student satisfies configured eligibility rules but institution verification is still pending.",
                        priority=_due_priority(deadline, now),
                        student_id=student.id,
                        drive_id=drive.id,
                        job_id=drive.job_id,
                        due_at=deadline,
                        details={"eligibility_summary": eligibility["summary"]},
                    )
                else:
                    key = f"drive:{drive.id}:eligible-not-applied:{student.id}"
                    active_keys.add(key)
                    _, was_created = _upsert_action(
                        db,
                        organization_id=organization_id,
                        source_key=key,
                        action_type="eligible_not_applied",
                        title=f"{student.full_name or 'Student'} has not applied to {drive.title}",
                        description="The student is currently eligible and the registration window is still open.",
                        priority=_due_priority(deadline, now),
                        student_id=student.id,
                        drive_id=drive.id,
                        job_id=drive.job_id,
                        due_at=deadline,
                        details={
                            "eligibility_summary": eligibility["summary"],
                            "company": job.recruiter.company_name if job.recruiter else None,
                            "role": job.title,
                        },
                    )
                created += int(was_created)
                updated += int(not was_created)
            elif not eligibility["eligible"] and application is None:
                failed = [item for item in eligibility["checks"] if not item["passed"]]
                if failed and all(item["key"] == "documents" for item in failed):
                    key = f"drive:{drive.id}:requirements:{student.id}"
                    active_keys.add(key)
                    _, was_created = _upsert_action(
                        db,
                        organization_id=organization_id,
                        source_key=key,
                        action_type="drive_requirement_blocker",
                        title=f"Resolve documents for {student.full_name or 'student'}",
                        description="Required drive documents are blocking an otherwise eligible application.",
                        priority=_due_priority(deadline, now),
                        student_id=student.id,
                        drive_id=drive.id,
                        job_id=drive.job_id,
                        due_at=deadline,
                        details={"reasons": eligibility["reasons"]},
                    )
                    created += int(was_created)
                    updated += int(not was_created)

    application_ids = [
        app.id
        for student in students
        for app in student.applications
    ]
    upcoming = (
        db.query(InterviewSchedule)
        .filter(
            InterviewSchedule.application_id.in_(application_ids),
            InterviewSchedule.scheduled_at > now,
            InterviewSchedule.scheduled_at <= now + timedelta(hours=72),
            InterviewSchedule.status == "scheduled",
        )
        .all()
        if application_ids
        else []
    )
    applications = {
        row.id: row
        for row in db.query(Application).filter(Application.id.in_(application_ids)).all()
    } if application_ids else {}
    student_by_id = {student.id: student for student in students}
    for interview in upcoming:
        application = applications.get(interview.application_id)
        if application is None:
            continue
        student = student_by_id.get(application.student_id)
        if student is None:
            continue
        recent_mock = (
            db.query(MockInterview)
            .filter(
                MockInterview.student_id == student.id,
                MockInterview.job_id == application.job_id,
                MockInterview.overall_score.is_not(None),
                MockInterview.created_at >= now - timedelta(days=14),
            )
            .first()
        )
        if recent_mock is not None:
            continue
        key = f"interview:{interview.id}:prep:{student.id}"
        active_keys.add(key)
        _, was_created = _upsert_action(
            db,
            organization_id=organization_id,
            source_key=key,
            action_type="interview_prep_due",
            title=f"Interview preparation due for {student.full_name or 'student'}",
            description=f"{interview.round_name} is scheduled within 72 hours and no recent scored role-specific mock is recorded.",
            priority=_due_priority(interview.scheduled_at, now),
            student_id=student.id,
            drive_id=interview.drive_id,
            job_id=application.job_id,
            due_at=interview.scheduled_at,
            details={"round_name": interview.round_name},
        )
        created += int(was_created)
        updated += int(not was_created)

    resolved = 0
    rows = (
        db.query(PlacementAction)
        .filter(
            PlacementAction.organization_id == organization_id,
            PlacementAction.status.in_(["open", "in_progress"]),
            PlacementAction.action_type.in_(SYSTEM_ACTION_TYPES),
        )
        .all()
    )
    for row in rows:
        if row.source_key not in active_keys:
            row.status = "resolved"
            row.resolved_at = now
            row.resolution_outcome = "condition_cleared"
            row.resolution_note = row.resolution_note or "Resolved automatically because the source condition is no longer active."
            resolved += 1

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "resolved": resolved,
        "active_conditions": len(active_keys),
        "synced_at": _iso(now),
    }


def _serialize_action(
    row: PlacementAction,
    *,
    students: dict[str, StudentProfile] | None = None,
    drives: dict[str, PlacementDrive] | None = None,
) -> dict:
    student = (students or {}).get(row.student_id or "")
    drive = (drives or {}).get(row.drive_id or "")
    job = drive.job if drive and drive.job else None
    return {
        "id": row.id,
        "action_type": row.action_type,
        "title": row.title,
        "description": row.description,
        "priority": row.priority,
        "status": row.status,
        "student_id": row.student_id,
        "student_name": student.full_name if student else None,
        "student_branch": student.branch if student else None,
        "drive_id": row.drive_id,
        "drive_title": drive.title if drive else None,
        "job_id": row.job_id,
        "job_title": job.title if job else None,
        "company_name": job.recruiter.company_name if job and job.recruiter else None,
        "owner_user_id": row.owner_user_id,
        "due_at": _iso(row.due_at),
        "detected_at": _iso(row.detected_at),
        "resolved_at": _iso(row.resolved_at),
        "resolution_note": row.resolution_note,
        "resolution_outcome": row.resolution_outcome,
        "details": row.details,
    }


def institution_action_centre(organization_id: str, db: Session) -> dict:
    now = utcnow()
    rows = (
        db.query(PlacementAction)
        .filter(PlacementAction.organization_id == organization_id)
        .order_by(PlacementAction.detected_at.desc())
        .all()
    )
    open_rows = [row for row in rows if row.status in {"open", "in_progress"}]
    open_rows.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(row.priority, 9),
            row.due_at is None,
            row.due_at or datetime.max,
            row.detected_at,
        )
    )
    student_ids = {row.student_id for row in open_rows if row.student_id}
    drive_ids = {row.drive_id for row in open_rows if row.drive_id}
    students = {
        row.id: row
        for row in db.query(StudentProfile).filter(StudentProfile.id.in_(student_ids)).all()
    } if student_ids else {}
    drives = {
        row.id: row
        for row in db.query(PlacementDrive).filter(PlacementDrive.id.in_(drive_ids)).all()
    } if drive_ids else {}
    drive_counts = Counter(row.drive_id for row in open_rows if row.drive_id)
    rescue_drives = []
    for drive_id, count in drive_counts.most_common():
        drive = drives.get(drive_id)
        if not drive:
            continue
        rescue_drives.append({
            "drive_id": drive.id,
            "drive_title": drive.title,
            "job_title": drive.job.title if drive.job else None,
            "company_name": drive.job.recruiter.company_name if drive.job and drive.job.recruiter else None,
            "open_actions": count,
            "deadline": _iso(drive.registration_deadline),
        })
    resolved_recent = sum(
        1
        for row in rows
        if row.status == "resolved" and row.resolved_at and row.resolved_at >= now - timedelta(days=30)
    )
    due_24h = sum(1 for row in open_rows if row.due_at and row.due_at <= now + timedelta(hours=24))
    return {
        "summary": {
            "open_actions": len(open_rows),
            "high_priority": sum(1 for row in open_rows if row.priority in {"critical", "high"}),
            "in_progress": sum(1 for row in open_rows if row.status == "in_progress"),
            "due_within_24h": due_24h,
            "resolved_last_30_days": resolved_recent,
            "rescue_drives": len(rescue_drives),
        },
        "actions": [
            _serialize_action(row, students=students, drives=drives)
            for row in open_rows[:100]
        ],
        "rescue_drives": rescue_drives[:20],
        "disclaimer": "Drive Rescue uses configured eligibility, deadlines and recorded workflow evidence. It does not predict student success or make hiring decisions.",
    }


def student_next_actions(student: StudentProfile, db: Session) -> list[dict]:
    """Return prioritized student actions without exposing unauthorized campus opportunities."""
    now = utcnow()
    actions: list[dict] = []
    missing = [
        label
        for label, value in (
            ("full name", student.full_name),
            ("branch", student.branch),
            ("graduation year", student.graduation_year),
            ("CGPA", student.cgpa),
            ("phone", student.phone),
        )
        if value in (None, "")
    ]
    if missing:
        actions.append({
            "key": "profile",
            "type": "profile_incomplete",
            "priority": "high",
            "title": "Complete your placement profile",
            "description": f"Add {', '.join(missing)} so eligibility checks use complete information.",
            "view": "profile",
            "due_at": None,
        })
    if student.resume is None:
        actions.append({
            "key": "resume",
            "type": "resume_missing",
            "priority": "high",
            "title": "Upload your current resume",
            "description": "Your resume is required for role-specific preparation and recruiter review.",
            "view": "resume",
            "due_at": None,
        })
    if student.organization_id and not student.is_verified:
        actions.append({
            "key": "verification",
            "type": "verification_pending",
            "priority": "medium",
            "title": "Institution verification is pending",
            "description": "Campus opportunities remain restricted until your placement office verifies the academic profile.",
            "view": "profile",
            "due_at": None,
        })

    if student.organization_id and student.is_verified and student.placement_opt_in:
        drives = (
            db.query(PlacementDrive)
            .filter(
                PlacementDrive.organization_id == student.organization_id,
                PlacementDrive.status == DriveStatus.open,
            )
            .all()
        )
        for drive in drives:
            deadline = drive.registration_deadline
            if deadline is not None and deadline <= now:
                continue
            job = drive.job
            if job is None or not job.is_active or _enum_value(job.approval_status) != ApprovalStatus.approved.value:
                continue
            if _application_for(student.id, drive, db) is not None:
                continue
            eligibility = evaluate_drive_eligibility(student, drive, db)
            if not eligibility["eligible"]:
                continue
            actions.append({
                "key": f"drive:{drive.id}",
                "type": "eligible_not_applied",
                "priority": _due_priority(deadline, now),
                "title": f"Apply to {drive.title}",
                "description": f"You are currently eligible for {job.title}" + (f" at {job.recruiter.company_name}" if job.recruiter else "") + ".",
                "view": "drives",
                "drive_id": drive.id,
                "job_id": job.id,
                "due_at": _iso(deadline),
            })

    application_ids = [application.id for application in student.applications]
    upcoming = (
        db.query(InterviewSchedule)
        .filter(
            InterviewSchedule.application_id.in_(application_ids),
            InterviewSchedule.scheduled_at > now,
            InterviewSchedule.scheduled_at <= now + timedelta(hours=72),
            InterviewSchedule.status == "scheduled",
        )
        .all()
        if application_ids
        else []
    )
    app_by_id = {application.id: application for application in student.applications}
    for interview in upcoming:
        application = app_by_id.get(interview.application_id)
        if not application:
            continue
        recent_mock = (
            db.query(MockInterview)
            .filter(
                MockInterview.student_id == student.id,
                MockInterview.job_id == application.job_id,
                MockInterview.overall_score.is_not(None),
                MockInterview.created_at >= now - timedelta(days=14),
            )
            .first()
        )
        if recent_mock:
            continue
        actions.append({
            "key": f"interview:{interview.id}",
            "type": "interview_prep_due",
            "priority": _due_priority(interview.scheduled_at, now),
            "title": f"Prepare for {interview.round_name}",
            "description": "Your interview is within 72 hours and no recent scored role-specific mock is recorded.",
            "view": "mock-interview",
            "due_at": _iso(interview.scheduled_at),
            "job_id": application.job_id,
        })

    if len(actions) < 5:
        evidence = readiness_evidence(student, db)
        next_action = evidence["next_best_action"]
        if not any(item["view"] == next_action["view"] for item in actions):
            actions.append({
                "key": "readiness",
                "type": "readiness_improvement",
                "priority": "normal",
                "title": next_action["title"],
                "description": next_action["reason"],
                "view": next_action["view"],
                "due_at": None,
            })
    actions.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(item.get("priority", "normal"), 9),
            item.get("due_at") is None,
            item.get("due_at") or "9999",
        )
    )
    return actions[:5]
