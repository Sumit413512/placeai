"""Read-only opportunity presentation; fictional previews never create database rows."""
from copy import deepcopy

BANNER = "/static/opportunity-workplace.webp"
DEMO = {
    "id": "technova-demo-preview", "title": "Graduate Software Engineer — Demo",
    "company_name": "TechNova Solutions — Demo", "is_demo": True, "is_preview": True,
    "description": "This is a fictional campus opportunity created to demonstrate PlaceAI. No employer is recruiting through this preview.\n\nAbout the role\nWork with a sample product team to build and test small web applications, write clear SQL queries, review code and explain technical decisions.\n\nResponsibilities\nDevelop and test simple features. Investigate defects using reproducible examples. Document your work and collaborate with a mentor.\n\nLearning tracks\nBackend development, frontend development, databases and software quality.",
    "job_type": "Full-time (illustrative)", "location": "Pune / Bengaluru — illustrative",
    "salary_range": "INR 4–6 LPA — illustrative only", "experience_required": "0–1 year — illustrative",
    "required_skills": ["Programming fundamentals", "SQL", "Problem solving", "Communication"],
    "preferred_roles": [], "visibility": "campus", "created_at": None, "deadline": None,
    "banner_url": BANNER, "logo_url": "/static/technova-demo.svg",
    "company": {"name": "TechNova Solutions — Demo", "about": "A fictional software company used only to demonstrate PlaceAI's opportunity experience. All role, compensation, eligibility and organization details in this preview are sample data.", "industry": "Software and IT services — illustrative", "size": "100–250 people — illustrative", "website": None, "contact": "TechNova campus team — fictional"},
    "criteria": [{"label": "Degree", "value": "B.E. / B.Tech — illustrative"}, {"label": "Branches", "value": "Computer Science, IT or related fields — illustrative"}, {"label": "Minimum CGPA", "value": "6.5 / 10 — illustrative"}, {"label": "Active backlogs", "value": "None — illustrative"}],
    "selection_process": ["Technical assessment — sample", "Technical interview — sample", "HR conversation — sample"],
    "registration_notes": "Preview available anytime. This is not a real vacancy; no registration deadline or application submission applies.",
    "eligibility": None, "policy": {"allowed": False, "reasons": []}, "already_applied": False, "can_apply": False,
}


def demo_opportunity():
    return deepcopy(DEMO)


def opportunity_detail(job, profile, db):
    from app.models import Application, DriveStage
    from app.placement_access import available_drive_for_job
    from app.services import job_out, evaluate_drive_eligibility, evaluate_placement_policies
    from app.trial_demo_access import is_trial_demo_job

    drive = available_drive_for_job(profile, job, db) if job.visibility == "campus" else None
    recruiter = job.recruiter
    result = job_out(job).model_dump(mode="json")
    result.update({"is_demo": is_trial_demo_job(job), "is_preview": False, "banner_url": BANNER,
                   "logo_url": None, "criteria": [], "selection_process": [], "eligibility": None,
                   "registration_notes": drive.notes if drive else None,
                   "company": {"name": result["company_name"], "industry": recruiter.industry if recruiter else None,
                               "website": recruiter.company_website if recruiter else None, "about": None, "size": None,
                               "contact": "Contact your placement office for this opportunity."}})
    if drive:
        result["eligibility"] = evaluate_drive_eligibility(profile, drive, db)
        labels = [("min_cgpa", "Minimum CGPA"), ("min_tenth_percentage", "10th minimum %"),
                  ("min_twelfth_percentage", "12th minimum %"), ("min_diploma_percentage", "Diploma minimum %"),
                  ("max_active_backlogs", "Maximum active backlogs"), ("max_historical_backlogs", "Maximum historical backlogs"),
                  ("max_academic_gap_months", "Maximum academic gap (months)"), ("work_authorization_required", "Work authorization")]
        result["criteria"] = [{"label": label, "value": str(getattr(drive, key))} for key, label in labels if getattr(drive, key) is not None]
        for label, values in [("Eligible branches", drive.allowed_branches), ("Graduation years", drive.allowed_graduation_years),
                              ("Required certifications", drive.required_certifications), ("Required documents", drive.required_documents)]:
            if values: result["criteria"].append({"label": label, "value": ", ".join(map(str, values))})
        result["criteria"].append({"label": "Already-placed students", "value": "Allowed" if drive.allow_placed_students else "Not allowed"})
        deadlines = [value for value in (job.deadline, drive.registration_deadline) if value]
        if deadlines: result["deadline"] = min(deadlines).isoformat()
        result["selection_process"] = [stage.name for stage in db.query(DriveStage).filter_by(drive_id=drive.id).order_by(DriveStage.order_index).all()]
    if result["is_demo"]:
        sample = demo_opportunity()
        for key in ("logo_url", "company", "criteria", "selection_process"):
            result[key] = sample[key]
        result["registration_notes"] = "This is a fictional demonstration assessment, not a real employer vacancy. Existing assessment access rules still apply."
    result["already_applied"] = db.query(Application.id).filter_by(student_id=profile.id, job_id=job.id).first() is not None
    result["policy"] = evaluate_placement_policies(profile, job, db)
    result["can_apply"] = not result["already_applied"] and result["policy"]["allowed"] and (not result["eligibility"] or result["eligibility"]["eligible"])
    return result
