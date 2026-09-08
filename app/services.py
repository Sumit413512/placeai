from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import (
    Application,
    AuditEvent,
    CustomFieldDefinition,
    CustomFieldValue,
    IncidentReport,
    InstitutionPolicy,
    Job,
    Notification,
    Offer,
    PlacementDrive,
    RecruiterProfile,
    StudentDocument,
    StudentProfile,
    User,
)
from app.schemas import (
    ApplicationOut,
    CompanyTrustAssessment,
    CompanyTrustCheck,
    JobOut,
    PlacementDriveOut,
    StudentBasicOut,
    StudentProfileOut,
)


def student_out(profile: StudentProfile) -> StudentProfileOut:
    out = StudentProfileOut.model_validate(profile)
    out.skills = profile.skills
    out.desired_roles = profile.desired_roles
    out.certifications = profile.certifications
    out.has_resume = profile.resume is not None
    return out


def job_out(job: Job) -> JobOut:
    out = JobOut.model_validate(job)
    out.required_skills = job.required_skills
    out.preferred_roles = job.preferred_roles
    out.company_name = job.recruiter.company_name if job.recruiter else None
    out.application_count = len(job.applications)
    out.target_organization_name = job.target_institution.name if getattr(job, "target_institution", None) else None
    return out


def application_out(application: Application) -> ApplicationOut:
    out = ApplicationOut.model_validate(application)
    if application.job:
        out.job_title = application.job.title
        out.job_type = application.job.job_type
        out.company_name = application.job.recruiter.company_name if application.job.recruiter else None
    if application.student:
        s = application.student
        out.student = StudentBasicOut(
            id=s.id,
            full_name=s.full_name,
            college=s.college,
            cgpa=s.cgpa,
            skills=s.skills,
            degree=s.degree,
            branch=s.branch,
            graduation_year=s.graduation_year,
        )
    return out


def _norm_set(values) -> set[str]:
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def evaluate_drive_eligibility(student: StudentProfile, drive: PlacementDrive, db: Session | None = None) -> dict:
    """Return an explainable eligibility decision for advanced campus rules."""
    checks: list[dict] = []

    def check(key: str, label: str, passed: bool, actual=None, required=None, reason: str | None = None):
        checks.append({
            "key": key,
            "label": label,
            "passed": bool(passed),
            "actual": actual,
            "required": required,
            "reason": None if passed else (reason or f"{label} requirement not met"),
        })

    check("cgpa", "CGPA", drive.min_cgpa is None or (student.cgpa is not None and student.cgpa >= drive.min_cgpa), student.cgpa, drive.min_cgpa, f"CGPA must be at least {drive.min_cgpa}")
    check("tenth", "10th percentage", drive.min_tenth_percentage is None or (student.tenth_percentage is not None and student.tenth_percentage >= drive.min_tenth_percentage), student.tenth_percentage, drive.min_tenth_percentage, f"10th percentage must be at least {drive.min_tenth_percentage}")
    check("twelfth", "12th percentage", drive.min_twelfth_percentage is None or (student.twelfth_percentage is not None and student.twelfth_percentage >= drive.min_twelfth_percentage), student.twelfth_percentage, drive.min_twelfth_percentage, f"12th percentage must be at least {drive.min_twelfth_percentage}")
    check("diploma", "Diploma percentage", drive.min_diploma_percentage is None or (student.diploma_percentage is not None and student.diploma_percentage >= drive.min_diploma_percentage), student.diploma_percentage, drive.min_diploma_percentage, f"Diploma percentage must be at least {drive.min_diploma_percentage}")
    check("active_backlogs", "Active backlogs", drive.max_active_backlogs is None or (student.active_backlogs or 0) <= drive.max_active_backlogs, student.active_backlogs or 0, drive.max_active_backlogs, f"Active backlogs must be {drive.max_active_backlogs} or fewer")
    check("historical_backlogs", "Historical backlogs", drive.max_historical_backlogs is None or (student.historical_backlogs or 0) <= drive.max_historical_backlogs, student.historical_backlogs or 0, drive.max_historical_backlogs, f"Historical backlogs must be {drive.max_historical_backlogs} or fewer")
    check("academic_gap", "Academic gap", drive.max_academic_gap_months is None or (student.academic_gap_months or 0) <= drive.max_academic_gap_months, student.academic_gap_months or 0, drive.max_academic_gap_months, f"Academic gap must be {drive.max_academic_gap_months} months or fewer")

    years = set(drive.allowed_graduation_years)
    check("graduation_year", "Graduation year", not years or student.graduation_year in years, student.graduation_year, sorted(years) if years else "Any", "Graduation year is outside the eligible batches")

    branches = _norm_set(drive.allowed_branches)
    check("branch", "Department / branch", not branches or (student.branch or "").strip().lower() in branches, student.branch, sorted(branches) if branches else "Any", "Department is not eligible for this drive")

    required_skills = _norm_set(drive.required_skills)
    student_skills = _norm_set(student.skills)
    missing_skills = sorted(required_skills - student_skills)
    check("skills", "Required skills", not missing_skills, sorted(student_skills), sorted(required_skills), f"Missing required skills: {', '.join(missing_skills)}")

    required_certs = _norm_set(drive.required_certifications)
    student_certs = _norm_set(student.certifications)
    missing_certs = sorted(required_certs - student_certs)
    check("certifications", "Required certifications", not missing_certs, sorted(student_certs), sorted(required_certs), f"Missing required certifications: {', '.join(missing_certs)}")

    if drive.work_authorization_required:
        check("work_authorization", "Work authorization", (student.work_authorization or "").strip().lower() == drive.work_authorization_required.strip().lower(), student.work_authorization, drive.work_authorization_required, "Required work authorization does not match")

    if not drive.allow_placed_students:
        check("placement_status", "Placement status", (student.placement_status or "unplaced") == "unplaced", student.placement_status, "unplaced", "Already placed students are not permitted for this drive")

    if db is not None and drive.required_documents:
        docs = db.query(StudentDocument).filter(StudentDocument.student_id == student.id).all()
        available = _norm_set(d.document_type for d in docs)
        missing_docs = sorted(_norm_set(drive.required_documents) - available)
        check("documents", "Required documents", not missing_docs, sorted(available), drive.required_documents, f"Missing required documents: {', '.join(missing_docs)}")

    # Simple custom rules allow colleges to add numeric thresholds without a code change.
    rules = drive.custom_eligibility_rules or {}
    for key, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        field = rule.get("field")
        op = rule.get("operator", ">=")
        target = rule.get("value")
        actual = getattr(student, field, None) if field else None
        passed = True
        try:
            if op == ">=": passed = actual is not None and actual >= target
            elif op == "<=": passed = actual is not None and actual <= target
            elif op == "==": passed = actual == target
            elif op == "in": passed = actual in target
        except Exception:
            passed = False
        check(f"custom:{key}", rule.get("label", key), passed, actual, target, rule.get("reason", f"Custom rule {key} not met"))

    failed = [c for c in checks if not c["passed"]]
    return {
        "eligible": not failed,
        "checks": checks,
        "reasons": [c["reason"] for c in failed],
        "summary": "Eligible" if not failed else f"Not eligible because: {failed[0]['reason']}",
    }


def is_student_eligible_for_drive(student: StudentProfile, drive: PlacementDrive) -> bool:
    return bool(evaluate_drive_eligibility(student, drive)["eligible"])


def drive_out(drive: PlacementDrive, db: Session) -> PlacementDriveOut:
    out = PlacementDriveOut.model_validate(drive)
    out.allowed_graduation_years = drive.allowed_graduation_years
    out.allowed_branches = drive.allowed_branches
    out.required_skills = drive.required_skills
    out.required_certifications = drive.required_certifications
    out.required_documents = drive.required_documents
    out.custom_eligibility_rules = drive.custom_eligibility_rules
    if drive.job:
        out.job_title = drive.job.title
        out.company_name = drive.job.recruiter.company_name if drive.job.recruiter else None
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == drive.organization_id).all()
    out.eligible_students = sum(1 for s in students if evaluate_drive_eligibility(s, drive, db)["eligible"])
    return out


def record_audit(db: Session, actor: User | None, action: str, *, organization_id: str | None = None, entity_type: str | None = None, entity_id: str | None = None, metadata: dict | None = None) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        organization_id=organization_id or (actor.organization_id if actor else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    event.details = metadata or {}
    db.add(event)
    return event


def create_notification(db: Session, user_id: str, title: str, message: str, *, organization_id: str | None = None, category: str = "general", priority: str = "normal", link: str | None = None) -> Notification:
    notification = Notification(
        user_id=user_id,
        organization_id=organization_id,
        title=title,
        message=message,
        category=category,
        priority=priority,
        link=link,
    )
    db.add(notification)
    return notification


PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "yahoo.co.in", "icloud.com", "proton.me", "protonmail.com"
}
SUSPICIOUS_TLDS = {"zip", "mov", "top", "click", "work", "buzz", "xyz"}


def _hostname(url: str | None) -> str:
    if not url:
        return ""
    value = url.strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        host = (urlparse(value).hostname or "").lower().strip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def company_trust_assessment(profile: RecruiterProfile, db: Session | None = None) -> CompanyTrustAssessment:
    """Evidence-based company verification centre; no claim of legal legitimacy."""
    checks: list[CompanyTrustCheck] = []
    risk_flags: list[str] = []

    def add(key: str, label: str, passed: bool, detail_ok: str, detail_missing: str, weight: int, partial: int = 0):
        earned = weight if passed else partial
        status = "verified" if passed else ("partial" if partial else "missing")
        checks.append(CompanyTrustCheck(
            key=key, label=label, status=status, detail=detail_ok if passed else detail_missing,
            weight=weight, earned=earned,
        ))

    website_host = _hostname(profile.company_website)
    website_ok = bool(website_host)
    identity_ok = bool((profile.company_name or "").strip() and (profile.industry or "").strip())
    email = (profile.user.email if profile.user else "").lower().strip()
    email_domain = email.split("@", 1)[1] if "@" in email else ""
    official_domain = (profile.official_email_domain or website_host or "").lower().strip()

    add("company_identity", "Company identity", bool((profile.company_name or "").strip() and (profile.industry or "").strip()), "Company name and industry are recorded.", "Company identity information is incomplete.", 6)
    cin = (profile.cin or "").strip().upper()
    gstin = (profile.gstin or "").strip().upper()
    cin_ok = bool(re.fullmatch(r"[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", cin))
    gstin_ok = bool(re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", gstin))
    add("cin", "CIN", cin_ok, "CIN is present and matches the expected structural format; registry validation is still required.", "CIN is missing or does not match the expected structural format.", 8, 2 if cin else 0)
    add("gstin", "GSTIN", gstin_ok, "GSTIN is present and matches the expected structural format; tax-registry validation is still required.", "GSTIN is missing or does not match the expected structural format.", 6, 2 if gstin else 0)
    if cin and not cin_ok:
        risk_flags.append("CIN format requires manual review")
    if gstin and not gstin_ok:
        risk_flags.append("GSTIN format requires manual review")
    add("website", "Official website", bool(website_host), f"Company website domain is {website_host}.", "No valid corporate website is present.", 8)

    domain_match = bool(official_domain and email_domain and email_domain not in PUBLIC_EMAIL_DOMAINS and (email_domain == official_domain or email_domain.endswith("." + official_domain) or official_domain.endswith("." + email_domain)))
    email_partial = 2 if email_domain and email_domain not in PUBLIC_EMAIL_DOMAINS else 0
    add("domain_email", "Official email domain", domain_match, "Recruiter email matches the recorded company domain.", "Recruiter email does not match the recorded company domain or uses a public email provider.", 10, email_partial)

    linkedin_ok = bool(_hostname(profile.linkedin_url) and "linkedin.com" in _hostname(profile.linkedin_url))
    add("linkedin", "LinkedIn / professional presence", linkedin_ok, "LinkedIn evidence is present.", "LinkedIn evidence has not been provided.", 5)
    add("address", "Company address", bool((profile.company_address or "").strip()), "Company address is recorded.", "Company address is missing.", 5)
    add("recruiter_identity", "Recruiter identity", bool((profile.full_name or "").strip() and (profile.designation or "").strip()), "Recruiter name and designation are recorded.", "Recruiter name/designation is incomplete.", 6)
    add("institution_verification", "Institution verification", bool(profile.is_verified), "Recruiter has been verified inside PlaceAI.", "Recruiter is not yet verified by an institution or platform administrator.", 12)
    add("institution_provisioning", "Placement-office provisioning", bool(profile.provisioned_by_organization_id), "Account was provisioned by a placement office.", "Account was not provisioned by a placement office.", 7)
    add("authorization_letter", "Recruitment authorization letter", bool(profile.authorization_letter_path), "Recruitment authorization evidence is on file.", "No authorization letter is on file.", 7)
    add("college_relationships", "Past college relationships", bool(profile.past_college_relationships), f"{len(profile.past_college_relationships)} prior college relationship(s) recorded.", "No prior college relationships are recorded.", 5)
    add("successful_placements", "Previous successful placements", (profile.previous_successful_placements or 0) > 0, f"{profile.previous_successful_placements} successful placement(s) recorded.", "No successful placement history is recorded yet.", 5)

    complaints = 0
    if db is not None:
        complaints = db.query(IncidentReport).filter(IncidentReport.recruiter_id == profile.id, IncidentReport.status.in_(["open", "investigating", "substantiated"])).count()
    complaint_ok = complaints == 0
    add("complaints", "Complaint history", complaint_ok, "No unresolved student incidents are recorded.", f"{complaints} unresolved incident report(s) require review.", 5)
    if complaints:
        risk_flags.append(f"{complaints} unresolved incident report(s)")

    consistency = max(0, min(100, int(profile.job_consistency_score or 0)))
    add("job_consistency", "Job-information consistency", consistency >= 70, f"Job information consistency score is {consistency}/100.", f"Job information consistency is only {consistency}/100 or not yet assessed.", 3, 1 if consistency >= 40 else 0)

    suspicious = bool(profile.suspicious_domain)
    if website_host and website_host.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS:
        suspicious = True
    if suspicious:
        risk_flags.append("Suspicious or high-risk domain signal")
    add("domain_risk", "Suspicious-domain detection", not suspicious, "No suspicious-domain flag is active.", "Domain requires manual review due to a suspicious signal.", 2)

    # Keep the familiar PlaceAI trust score based on core onboarding evidence, while
    # exposing a stricter verification-confidence score for the full dossier. This
    # avoids conflating a well-controlled recruiter account with government/company
    # registration evidence that may still need manual verification.
    core_score = 0
    core_score += 30 if profile.is_verified else 0
    core_score += 20 if profile.provisioned_by_organization_id else 0
    core_score += 15 if website_ok else 0
    core_score += 20 if domain_match else email_partial
    core_score += 10 if linkedin_ok else 0
    core_score += 5 if identity_ok else 0
    score = max(0, min(100, core_score))

    dossier_score = max(0, min(100, sum(c.earned for c in checks)))
    # Risk flags should materially affect confidence/status, but do not silently erase evidence.
    confidence = max(0, min(100, dossier_score - min(25, len(risk_flags) * 12)))
    if risk_flags or confidence < 35:
        verification_status = "High Risk"
    elif profile.is_verified and confidence >= 80 and (cin_ok or gstin_ok):
        verification_status = "Verified"
    elif confidence >= 55:
        verification_status = "Partially Verified"
    else:
        verification_status = "Manual Review Required"

    # `level` remains the backwards-compatible core-account trust classification;
    # `verification_status` is the stricter enterprise dossier result.
    if profile.is_verified and score >= 75:
        level = "verified"
    elif score >= 60:
        level = "review"
    elif score >= 35:
        level = "caution"
    else:
        level = "high_risk"

    label = verification_status
    return CompanyTrustAssessment(
        score=score,
        level=level,
        label=label,
        checks=checks,
        disclaimer="Verification confidence is an evidence-screening aid, not a government or legal certification. CIN, GSTIN, authorization letters and company claims must still be independently validated by the placement office.",
        verification_status=verification_status,
        confidence=confidence,
        risk_flags=risk_flags,
    )


def placement_readiness(student: StudentProfile, db: Session) -> dict:
    """Evidence-backed readiness, not a prediction of hiring success."""
    profile_fields = [student.full_name, student.degree, student.branch, student.graduation_year, student.cgpa, student.phone, student.linkedin_url]
    profile_score = round(sum(bool(x) for x in profile_fields) / len(profile_fields) * 100)
    resume_score = 0
    if student.resume:
        resume_score = 65 + (20 if student.resume.is_parsed else 0) + (15 if student.ai_summary else 0)
    skills_score = min(100, len(student.skills) * 12 + len(student.certifications) * 7)
    desired = _norm_set(student.desired_roles)
    role_alignment = min(100, 40 + len(desired) * 15) if desired else 35
    # Real interview evidence is intentionally separated from AI mock-interview evidence.
    completed_interviews = len([m for m in student.mock_interviews if m.overall_score is not None])
    interview_readiness = min(100, 45 + completed_interviews * 15)
    academic = 100
    if student.cgpa is None: academic -= 25
    if student.active_backlogs: academic -= min(35, student.active_backlogs * 10)
    if student.academic_gap_months: academic -= min(20, student.academic_gap_months // 6 * 5)
    academic = max(0, academic)
    parsed = student.resume.ai_parsed_data if student.resume else None
    project_evidence = 55
    if parsed and isinstance(parsed, dict):
        exp = parsed.get("experience") or []
        project_evidence = min(100, 55 + len(exp) * 10)
    components = {
        "Profile completeness": profile_score,
        "Resume strength": resume_score,
        "Technical skills": skills_score,
        "Role alignment": role_alignment,
        "Interview readiness": interview_readiness,
        "Academic eligibility": academic,
        "Project evidence": project_evidence,
    }
    weights = {
        "Profile completeness": .14,
        "Resume strength": .16,
        "Technical skills": .19,
        "Role alignment": .13,
        "Interview readiness": .14,
        "Academic eligibility": .14,
        "Project evidence": .10,
    }
    score = round(sum(components[k] * weights[k] for k in components))
    actions: list[str] = []
    if profile_score < 85: actions.append("Complete missing academic and contact fields and keep institution-verifiable details current.")
    if resume_score < 75: actions.append("Upload a current text-based resume and run the resume analysis after reviewing your profile data.")
    if skills_score < 75: actions.append("Add evidence-backed technical skills and certifications relevant to your target roles.")
    if interview_readiness < 75: actions.append("Complete role-specific mock interviews and review weak answer areas.")
    if project_evidence < 75: actions.append("Add measurable project outcomes, responsibilities and technologies to your resume.")
    if not actions: actions.append("Maintain current evidence and focus preparation on the next eligible drive.")
    return {
        "score": score,
        "components": [{"name": k, "score": int(v)} for k, v in components.items()],
        "recommended_actions": actions[:5],
        "disclaimer": "Placement Readiness measures profile evidence and preparation signals. It does not predict or guarantee employment.",
    }


def evaluate_placement_policies(student: StudentProfile, job: Job, db: Session) -> dict:
    org_id = student.organization_id
    if not org_id:
        return {"allowed": True, "reasons": [], "evaluated_policies": [], "exceptions": []}
    policies = db.query(InstitutionPolicy).filter(InstitutionPolicy.organization_id == org_id, InstitutionPolicy.is_active.is_(True)).all()
    reasons: list[str] = []
    exceptions: list[str] = []
    evaluated: list[str] = []
    current_offers = db.query(Offer).join(Application, Offer.application_id == Application.id).filter(
        Application.student_id == student.id,
        Offer.status.in_(["issued", "accepted", "joining_confirmed"]),
    ).all()
    accepted_ctcs = [o.ctc_lpa for o in current_offers if o.status in {"accepted", "joining_confirmed"} and o.ctc_lpa is not None]
    highest_accepted_ctc = max(accepted_ctcs) if accepted_ctcs else None
    target_ctc = extract_ctc_from_salary_range(job.salary_range)
    is_internship = "intern" in (job.job_type or "").lower()

    for policy in policies:
        rules = policy.rules
        evaluated.append(policy.policy_key)
        policy_reasons: list[str] = []
        max_offers = rules.get("max_offers_per_student", rules.get("max_offers"))
        if max_offers is not None and len(current_offers) >= int(max_offers):
            policy_reasons.append(f"{policy.name}: maximum {max_offers} active offer(s) permitted")
        if rules.get("block_if_placed") and student.placement_status == "placed":
            policy_reasons.append(f"{policy.name}: already placed students cannot participate")

        min_next = rules.get("min_next_offer_lpa")
        if min_next is not None and student.placement_status == "placed" and target_ctc is not None and target_ctc < float(min_next):
            policy_reasons.append(f"{policy.name}: next eligible opportunity must be at least {float(min_next):g} LPA")

        multiplier = rules.get("placed_salary_floor_multiplier")
        if multiplier is not None and highest_accepted_ctc is not None and target_ctc is not None:
            required = round(highest_accepted_ctc * float(multiplier), 2)
            if target_ctc < required:
                policy_reasons.append(f"{policy.name}: opportunity must be at least {required:g} LPA after the current accepted offer")

        internship_non_blocking = rules.get("internship_offers_do_not_block") or rules.get("internship_blocks_placement") is False
        if is_internship and internship_non_blocking:
            policy_reasons = [r for r in policy_reasons if "offer" not in r.lower() and "placed" not in r.lower()]
            exceptions.append(f"{policy.name}: internship exception applied")

        dream_threshold = rules.get("dream_company_min_ctc_lpa")
        dream_exception = bool(rules.get("dream_company_exception"))
        if dream_exception and dream_threshold is not None and target_ctc is not None and target_ctc >= float(dream_threshold):
            if policy_reasons:
                exceptions.append(f"{policy.name}: dream-company salary exception applied at {target_ctc:g} LPA")
            policy_reasons = []

        reasons.extend(policy_reasons)
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "evaluated_policies": evaluated,
        "exceptions": exceptions,
        "current_active_offers": len(current_offers),
        "highest_accepted_ctc_lpa": highest_accepted_ctc,
        "target_ctc_lpa": target_ctc,
    }


def institution_attention_centre(organization_id: str, db: Session) -> dict:
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == organization_id).all()
    incomplete = [s for s in students if not all([s.full_name, s.branch, s.graduation_year, s.cgpa, s.phone])]
    no_resume = [s for s in students if not s.resume]
    no_activity = []
    no_interview = []
    for s in students:
        if not s.applications:
            no_activity.append(s)
        if not any((a.status.value if hasattr(a.status, "value") else a.status) == "interview" for a in s.applications):
            no_interview.append(s)
    return {
        "total_students": len(students),
        "signals": [
            {"key": "incomplete_profiles", "label": "Incomplete profiles", "count": len(incomplete), "severity": "high" if len(incomplete) else "low"},
            {"key": "no_resume", "label": "No resume uploaded", "count": len(no_resume), "severity": "high" if len(no_resume) else "low"},
            {"key": "no_applications", "label": "No application activity", "count": len(no_activity), "severity": "medium" if len(no_activity) else "low"},
            {"key": "no_interviews", "label": "No interview activity", "count": len(no_interview), "severity": "medium" if len(no_interview) else "low"},
        ],
        "students": {
            "incomplete_profiles": [{"id": s.id, "name": s.full_name, "branch": s.branch} for s in incomplete[:25]],
            "no_resume": [{"id": s.id, "name": s.full_name, "branch": s.branch} for s in no_resume[:25]],
            "no_applications": [{"id": s.id, "name": s.full_name, "branch": s.branch} for s in no_activity[:25]],
            "no_interviews": [{"id": s.id, "name": s.full_name, "branch": s.branch} for s in no_interview[:25]],
        },
    }


def institution_analytics_v2(organization_id: str, db: Session) -> dict:
    students = db.query(StudentProfile).filter(StudentProfile.organization_id == organization_id).all()
    student_ids = [s.id for s in students]
    applications = db.query(Application).filter(Application.student_id.in_(student_ids)).all() if student_ids else []
    offers = db.query(Offer).join(Application, Offer.application_id == Application.id).filter(Application.student_id.in_(student_ids)).all() if student_ids else []
    accepted = [o for o in offers if o.status in {"accepted", "joining_confirmed"}]
    ctc = [o.ctc_lpa for o in accepted if o.ctc_lpa is not None]
    sorted_ctc = sorted(ctc)
    median = None
    if sorted_ctc:
        n = len(sorted_ctc)
        median = sorted_ctc[n // 2] if n % 2 else round((sorted_ctc[n // 2 - 1] + sorted_ctc[n // 2]) / 2, 2)

    app_by_id = {a.id: a for a in applications}
    placed_student_ids = {a.student_id for a in applications if (a.status.value if hasattr(a.status, "value") else a.status) in {"hired"}}
    for o in accepted:
        a = app_by_id.get(o.application_id)
        if a:
            placed_student_ids.add(a.student_id)

    branch_counts = Counter((s.branch or "Unknown") for s in students)
    branch_placed = Counter((s.branch or "Unknown") for s in students if s.id in placed_student_ids)
    by_department = [{
        "department": b,
        "students": count,
        "placed": branch_placed.get(b, 0),
        "placement_rate": round(branch_placed.get(b, 0) / count * 100, 1) if count else 0,
    } for b, count in branch_counts.most_common()]

    recruiters = Counter()
    for a in applications:
        if a.job and a.job.recruiter:
            recruiters[a.job.recruiter.company_name or "Company"] += 1

    # Monthly outcome trend, based on accepted/joining-confirmed offer creation.
    month_counts = Counter()
    for o in accepted:
        when = o.created_at or o.joining_date
        if when:
            month_counts[when.strftime("%Y-%m")] += 1
    monthly_trend = [{"month": month, "placements": month_counts[month]} for month in sorted(month_counts)]

    # Per-drive conversion makes it obvious where campus funnels are leaking.
    drives = db.query(PlacementDrive).filter(PlacementDrive.organization_id == organization_id).all()
    drive_conversion = []
    offers_by_app = {o.application_id for o in offers}
    accepted_by_app = {o.application_id for o in accepted}
    for d in drives:
        d_apps = [a for a in applications if a.drive_id == d.id]
        d_offers = [a for a in d_apps if a.id in offers_by_app]
        d_accepted = [a for a in d_apps if a.id in accepted_by_app]
        drive_conversion.append({
            "drive_id": d.id,
            "drive": d.title,
            "applications": len(d_apps),
            "offers": len(d_offers),
            "accepted": len(d_accepted),
            "application_to_offer": round(len(d_offers) / len(d_apps) * 100, 1) if d_apps else 0,
            "offer_acceptance": round(len(d_accepted) / len(d_offers) * 100, 1) if d_offers else 0,
        })

    internship_apps = [a for a in applications if a.job and "intern" in (a.job.job_type or "").lower()]
    internship_offer_app_ids = {o.application_id for o in offers if app_by_id.get(o.application_id) in internship_apps}
    ppo_confirmed = [o for o in offers if (o.ppo_status or "").strip().lower() in {"confirmed", "offered", "accepted"}]
    internship_ppo_conversion = round(len(ppo_confirmed) / len(internship_apps) * 100, 1) if internship_apps else 0

    unplaced = [s for s in students if s.id not in placed_student_ids]
    unplaced_ids = {s.id for s in unplaced}
    app_counts = Counter(a.student_id for a in applications)
    interview_ids = {a.student_id for a in applications if (a.pipeline_stage_key or "").startswith(("technical-", "hr-")) or (a.status.value if hasattr(a.status, "value") else a.status) == "interview"}
    offer_pending_ids = {app_by_id[o.application_id].student_id for o in offers if o.application_id in app_by_id and o.status == "issued"}
    unplaced_segmentation = [
        {"segment": "No applications", "count": sum(1 for sid in unplaced_ids if app_counts.get(sid, 0) == 0)},
        {"segment": "Applied, no interview yet", "count": sum(1 for sid in unplaced_ids if app_counts.get(sid, 0) > 0 and sid not in interview_ids and sid not in offer_pending_ids)},
        {"segment": "Interview activity", "count": sum(1 for sid in unplaced_ids if sid in interview_ids and sid not in offer_pending_ids)},
        {"segment": "Offer decision pending", "count": sum(1 for sid in unplaced_ids if sid in offer_pending_ids)},
    ]

    return {
        "placement_rate": round(len(placed_student_ids) / len(students) * 100, 1) if students else 0,
        "median_ctc": median,
        "average_ctc": round(sum(ctc) / len(ctc), 2) if ctc else None,
        "highest_ctc": max(ctc) if ctc else None,
        "offers_generated": len(offers),
        "unique_students_placed": len(placed_student_ids),
        "company_participation": len(recruiters),
        "offer_acceptance_rate": round(len(accepted) / len(offers) * 100, 1) if offers else 0,
        "application_to_offer_conversion": round(len(offers) / len(applications) * 100, 1) if applications else 0,
        "department_breakdown": by_department,
        "top_companies": [{"company": k, "applications": v} for k, v in recruiters.most_common(10)],
        "monthly_placement_trend": monthly_trend,
        "drive_conversion": drive_conversion,
        "internship_applications": len(internship_apps),
        "internship_offers": len(internship_offer_app_ids),
        "ppo_confirmed": len(ppo_confirmed),
        "internship_ppo_conversion": internship_ppo_conversion,
        "unplaced_students": len(unplaced),
        "unplaced_segmentation": unplaced_segmentation,
    }


def extract_ctc_from_salary_range(value: str | None) -> float | None:
    if not value:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))]
    if not nums:
        return None
    # If salary looks monthly, do not pretend it is LPA.
    if "month" in value.lower() or "/mo" in value.lower():
        return None
    return max(nums)
