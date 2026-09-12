from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.database import get_db
from app.dependencies import require_institution_admin
from app.models import (
    Application,
    AuditEvent,
    ApplicationStatus,
    ApprovalStatus,
    DriveStatus,
    DriveStage,
    Job,
    Organization,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.schemas import (
    AdminUserProvision,
    AuditEventOut,
    ApplicationOut,
    InstitutionDashboardOut,
    InstitutionStudentCreate,
    JobApprovalUpdate,
    JobOut,
    OrganizationOut,
    PlacementDriveCreate,
    PlacementDriveOut,
    PlacementDriveUpdate,
    RecruiterProfileOut,
    CompanyTrustAssessment,
    StudentProfileOut,
    StudentVerificationUpdate,
    UserOut,
)
from app.services import application_out, company_trust_assessment, create_notification, drive_out, job_out, record_audit, student_out
from app.utils import get_hashed_password

router = APIRouter(prefix="/institutions", tags=["Institution / TPO"])


def _org(current_user: User, db: Session) -> Organization:
    if current_user.role == UserRole.platform_admin and not current_user.organization_id:
        raise HTTPException(status_code=400, detail="Platform admin must use platform endpoints to select an institution")
    org = db.query(Organization).filter(Organization.id == current_user.organization_id, Organization.is_active.is_(True)).first()
    if not org:
        raise HTTPException(status_code=403, detail="Your account is not linked to an active institution")
    return org


def _deadline_has_passed(value: datetime | None) -> bool:
    if value is None:
        return False
    deadline = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return deadline <= datetime.now(timezone.utc)


def _spreadsheet_safe_cell(value: object) -> object:
    """Prevent CSV cells from being interpreted as spreadsheet formulas."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@router.get("/me", response_model=OrganizationOut)
def institution_profile(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    return _org(current_user, db)


@router.get("/dashboard", response_model=InstitutionDashboardOut)
def dashboard(
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


@router.get("/students", response_model=List[StudentProfileOut])
def list_students(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org.id).order_by(StudentProfile.full_name.asc()).limit(1000).all()
    return [student_out(s) for s in students]


@router.post("/students", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_student(data: InstitutionStudentCreate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    if db.query(User).filter(User.email == data.email.lower()).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="This username is already taken")
    user = User(
        email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password),
        role=UserRole.student, organization_id=org.id, must_change_password=True,
    )
    db.add(user)
    db.flush()
    profile = StudentProfile(
        user_id=user.id, organization_id=org.id, college=org.name, full_name=data.full_name,
        degree=data.degree, branch=data.branch, graduation_year=data.graduation_year, cgpa=data.cgpa,
        is_verified=True,
    )
    db.add(profile)
    db.flush()
    record_audit(db, current_user, "institution.student.provisioned", organization_id=org.id, entity_type="student_profile", entity_id=profile.id, metadata={"email": user.email, "name": data.full_name, "verified": True})
    db.commit()
    db.refresh(user)
    return user


@router.patch("/students/{student_id}/verification", response_model=StudentProfileOut)
def verify_student(student_id: str, data: StudentVerificationUpdate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id, StudentProfile.organization_id == org.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    student.is_verified = data.is_verified
    record_audit(db, current_user, "institution.student.verification_changed", organization_id=org.id, entity_type="student_profile", entity_id=student.id, metadata={"is_verified": data.is_verified})
    db.commit()
    db.refresh(student)
    return student_out(student)


@router.post("/import/students.csv")
async def import_students_csv(file: UploadFile = File(...), current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    filename = (file.filename or "students.csv").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV must be 2 MB or smaller")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    required = {"full_name", "email", "username", "temporary_password"}
    if not reader.fieldnames or not required.issubset({(x or "").strip() for x in reader.fieldnames}):
        raise HTTPException(status_code=400, detail="CSV headers must include full_name,email,username,temporary_password")

    created = 0
    errors = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > 1001:
            errors.append({"row": row_number, "error": "Import limited to 1000 rows per file"})
            break
        try:
            data = InstitutionStudentCreate(
                email=(row.get("email") or "").strip(),
                username=(row.get("username") or "").strip(),
                full_name=(row.get("full_name") or "").strip(),
                temporary_password=(row.get("temporary_password") or "").strip(),
                degree=(row.get("degree") or "").strip() or None,
                branch=(row.get("branch") or "").strip() or None,
                graduation_year=int(row["graduation_year"]) if (row.get("graduation_year") or "").strip() else None,
                cgpa=float(row["cgpa"]) if (row.get("cgpa") or "").strip() else None,
            )
        except (ValidationError, ValueError) as exc:
            errors.append({"row": row_number, "error": str(exc).splitlines()[0][:240]})
            continue

        if db.query(User).filter((User.email == str(data.email).lower()) | (User.username == data.username)).first():
            errors.append({"row": row_number, "error": "Email or username already exists"})
            continue
        user = User(
            email=str(data.email).lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password),
            role=UserRole.student, organization_id=org.id, must_change_password=True,
        )
        db.add(user)
        db.flush()
        profile = StudentProfile(
            user_id=user.id, organization_id=org.id, college=org.name, full_name=data.full_name,
            degree=data.degree, branch=data.branch, graduation_year=data.graduation_year, cgpa=data.cgpa,
            is_verified=True,
        )
        db.add(profile)
        created += 1

    record_audit(db, current_user, "institution.students.bulk_imported", organization_id=org.id, entity_type="student_profile", metadata={"created": created, "errors": len(errors), "filename": file.filename or "students.csv", "verified_at_creation": True})
    db.commit()
    return {"created": created, "failed": len(errors), "errors": errors[:100]}


@router.get("/recruiters", response_model=List[RecruiterProfileOut])
def list_recruiters(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    recruiter_ids = {j.recruiter_id for j in db.query(Job).filter(Job.target_organization_id == org.id).all()}
    recruiter_ids.update(row[0] for row in db.query(RecruiterProfile.id).filter(RecruiterProfile.provisioned_by_organization_id == org.id).all())
    if not recruiter_ids:
        return []
    return db.query(RecruiterProfile).filter(RecruiterProfile.id.in_(recruiter_ids)).order_by(RecruiterProfile.company_name.asc()).all()


@router.get("/recruiters/{recruiter_id}/trust-review", response_model=CompanyTrustAssessment)
def recruiter_trust_review(recruiter_id: str, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    profile = db.query(RecruiterProfile).filter(RecruiterProfile.id == recruiter_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    linked = profile.provisioned_by_organization_id == org.id or db.query(Job.id).filter(
        Job.recruiter_id == profile.id, Job.target_organization_id == org.id
    ).first() is not None
    if not linked:
        raise HTTPException(status_code=404, detail="Recruiter is not linked to this institution")
    return company_trust_assessment(profile, db)


@router.post("/recruiters", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def provision_recruiter(data: AdminUserProvision, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    if db.query(User).filter(User.email == data.email.lower()).first() or db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Email or username already exists")
    user = User(email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter, must_change_password=True)
    db.add(user)
    db.flush()
    profile = RecruiterProfile(user_id=user.id, full_name=data.full_name, company_name=data.company_name, is_verified=True, provisioned_by_organization_id=org.id)
    db.add(profile)
    db.flush()
    record_audit(db, current_user, "institution.recruiter.provisioned", organization_id=org.id, entity_type="recruiter_profile", entity_id=profile.id, metadata={"email": user.email, "company": data.company_name})
    db.commit()
    db.refresh(user)
    return user


@router.get("/jobs", response_model=List[JobOut])
def institution_jobs(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    jobs = db.query(Job).filter(Job.target_organization_id == org.id).order_by(Job.created_at.desc()).all()
    return [job_out(j) for j in jobs]


@router.patch("/jobs/{job_id}/approval", response_model=JobOut)
def approve_job(
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


@router.get("/drives", response_model=List[PlacementDriveOut])
def list_drives(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    drives = db.query(PlacementDrive).filter(PlacementDrive.organization_id == org.id).order_by(PlacementDrive.created_at.desc()).all()
    return [drive_out(d, db) for d in drives]


@router.post("/drives", response_model=PlacementDriveOut, status_code=status.HTTP_201_CREATED)
def create_drive(data: PlacementDriveCreate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    job = db.query(Job).filter(Job.id == data.job_id, Job.target_organization_id == org.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job is not targeted to this institution")
    if job.approval_status != ApprovalStatus.approved or not job.is_active:
        raise HTTPException(status_code=400, detail="Approve and activate the campus job before opening a placement drive")
    if data.status.value == DriveStatus.open.value and _deadline_has_passed(data.registration_deadline):
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
    default_stages = [("registration","Registration","registration"),("eligibility-screening","Eligibility Screening","screening"),("online-assessment","Online Assessment","assessment"),("technical-round-1","Technical Round 1","interview"),("technical-round-2","Technical Round 2","interview"),("hr-interview","HR Interview","interview"),("offer","Offer","offer"),("joined","Joined","terminal")]
    for idx, (key, name, stype) in enumerate(default_stages):
        db.add(DriveStage(drive_id=drive.id, stage_key=key, name=name, order_index=idx, stage_type=stype, is_terminal=(key == "joined")))
    record_audit(db, current_user, "institution.drive.created", organization_id=org.id, entity_type="placement_drive", entity_id=drive.id, metadata={"job_id": job.id, "title": drive.title, "status": drive.status.value})
    db.commit()
    db.refresh(drive)
    return drive_out(drive, db)


@router.put("/drives/{drive_id}", response_model=PlacementDriveOut)
def update_drive(drive_id: str, data: PlacementDriveUpdate, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id, PlacementDrive.organization_id == org.id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Placement drive not found")
    changes = data.model_dump(exclude_unset=True)
    target_status = changes.get("status", drive.status)
    target_status_value = target_status.value if hasattr(target_status, "value") else str(target_status)
    target_deadline = changes.get("registration_deadline", drive.registration_deadline)
    if target_status_value == DriveStatus.open.value and _deadline_has_passed(target_deadline):
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
    record_audit(db, current_user, "institution.drive.updated", organization_id=org.id, entity_type="placement_drive", entity_id=drive.id, metadata={"title": drive.title, "status": drive.status.value})
    db.commit()
    db.refresh(drive)
    return drive_out(drive, db)


@router.delete("/drives/{drive_id}", status_code=204)
def delete_drive(drive_id: str, current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    """Archive a drive without deleting application and stage history."""
    org = _org(current_user, db)
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id, PlacementDrive.organization_id == org.id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Placement drive not found")
    drive.status = DriveStatus.closed
    record_audit(db, current_user, "institution.drive.archived", organization_id=org.id, entity_type="placement_drive", entity_id=drive.id, metadata={"title": drive.title})
    db.commit()


@router.get("/audit", response_model=List[AuditEventOut])
def audit_log(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    events = db.query(AuditEvent).filter(AuditEvent.organization_id == org.id).order_by(AuditEvent.created_at.desc()).limit(500).all()
    return [AuditEventOut(
        id=e.id, actor_user_id=e.actor_user_id, actor_email=e.actor.email if e.actor else None, action=e.action,
        entity_type=e.entity_type, entity_id=e.entity_id, metadata=e.details, created_at=e.created_at,
    ) for e in events]


@router.get("/applications", response_model=List[ApplicationOut])
def institution_applications(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    job_ids = [row[0] for row in db.query(Job.id).filter(Job.target_organization_id == org.id).all()]
    if not job_ids:
        return []
    apps = db.query(Application).filter(Application.job_id.in_(job_ids)).order_by(Application.applied_at.desc()).limit(3000).all()
    return [application_out(a) for a in apps]


@router.get("/export/students.csv")
def export_students(current_user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = _org(current_user, db)
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == org.id).order_by(StudentProfile.full_name.asc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Email", "Degree", "Branch", "Graduation Year", "CGPA", "Verified", "Skills"])
    for s in students:
        row = [s.full_name, s.user.email if s.user else "", s.degree, s.branch, s.graduation_year, s.cgpa, s.is_verified, ", ".join(s.skills)]
        writer.writerow([_spreadsheet_safe_cell(value) for value in row])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{org.slug}-students.csv"'})
