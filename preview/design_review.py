"""Run the design review against disposable sample records on a separate host."""

import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
origin = os.getenv("DESIGN_REVIEW_ORIGIN") or "https://" + os.environ["RENDER_EXTERNAL_HOSTNAME"]
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL="sqlite:////tmp/placeai-design-review.db",
    BASE_URL=origin,
    PUBLIC_APP_URL=origin,
    ALLOWED_ORIGINS=origin,
    JWT_SECRET_KEY=secrets.token_urlsafe(48),
    JWT_REFRESH_SECRET_KEY=secrets.token_urlsafe(48),
    AUTO_CREATE_SCHEMA="true",
    DEV_SHOW_RESET_TOKEN="false",
    LEARNING_WORKER_IN_PROCESS="false",
    ASSESSMENT_WORKER_IN_PROCESS="false",
)

import uvicorn

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import (
    Application, Job, MockInterview, Organization, OrganizationType,
    RecruiterProfile, StudentProfile, User, UserRole,
)
from app.roadmap_models import CareerRoadmap
from app.utils import get_hashed_password


@app.middleware("http")
async def review_only(request, call_next):
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def seed():
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        if db.query(Organization).filter_by(slug="design-review-campus").first():
            return
        campus = Organization(name="Review Campus", slug="design-review-campus",
                              organization_type=OrganizationType.institution)
        employer = Organization(name="Juniper Systems", slug="design-review-employer",
                                organization_type=OrganizationType.employer)
        db.add_all([campus, employer])
        db.flush()
        password = get_hashed_password(os.environ["REVIEW_PASSWORD"], check_breach=False)
        accounts = {}
        for role in UserRole:
            org = {UserRole.platform_admin: None, UserRole.recruiter: employer.id}.get(role, campus.id)
            user = User(email=role.value.replace("_", ".") + "@preview.example.com",
                        username="Review " + role.value.replace("_", " ").title(),
                        role=role, email_verified=True, hashed_password=password, organization_id=org)
            accounts[role] = user
            db.add(user)
        db.flush()
        student = StudentProfile(user_id=accounts[UserRole.student].id, organization_id=campus.id,
                                 full_name="Review Student", college=campus.name, degree="B.Tech",
                                 branch="Computer Science", graduation_year=2027, cgpa=8.4,
                                 skills_json='["Python", "SQL"]', is_verified=True)
        recruiter = RecruiterProfile(user_id=accounts[UserRole.recruiter].id, full_name="Review Recruiter",
                                     company_name=employer.name, is_verified=True,
                                     provisioned_by_organization_id=campus.id)
        db.add_all([student, recruiter])
        db.flush()
        job = Job(recruiter_id=recruiter.id, title="Graduate Data Engineer", location="Pune",
                  description="Build reliable data pipelines and help maintain analytics datasets.",
                  visibility="campus", target_organization_id=campus.id,
                  required_skills_json='["Python","SQL"]')
        db.add(job)
        db.flush()
        db.add(Application(student_id=student.id, job_id=job.id))
        for score in (68, 84):
            db.add(MockInterview(student_id=student.id, job_id=job.id,
                                 questions_json="[]", answers_json="[]", overall_score=score))

        phases = []
        for index, (name, days, skill, project) in enumerate([
            ("Strengthen SQL fundamentals", 10, "SQL", "Campus hiring data explorer"),
            ("Build reliable pipelines", 18, "Python", "Incremental data ingestion"),
            ("Model an analytics warehouse", 14, "Data modelling", "Dimensional warehouse"),
            ("Deploy and document your work", 12, "Pipeline observability", "Production handoff"),
        ], start=1):
            phases.append({"phase": index, "name": name, "days": days,
                           "outcomes": [f"Demonstrate {skill} with a working project."],
                           "practice": ["Build an example, test it and explain your choices."],
                           "skills": [{"name": skill, "level": "working"}],
                           "projects": [{"title": project, "scope": f"Apply {skill} to a sample dataset.",
                                         "deliverables": ["A working example and a short README"]}],
                           "milestone": f"Publish and explain your {project.lower()}."})
        db.add(CareerRoadmap(
            student_id=student.id, title="Data Engineering Roadmap", target_role="Data Engineer",
            input_json=json.dumps({"target_roles": ["Data Engineer"], "current_skills": ["Python"]}),
            market_snapshot_json=json.dumps({"region": "India", "in_demand_skills": ["SQL", "Data modelling", "Pipeline observability"],
                                             "market_notes": ["Sample roadmap for the interface review."]}),
            roadmap_json=json.dumps({"estimated_days": 54, "weekly_hours": 8, "phases": phases,
                                     "portfolio_plan": ["Publish a README with reproducible steps."],
                                     "interview_preparation": ["Explain your pipeline failure handling."],
                                     "disclaimer": "Illustrative roadmap for the PlaceAI design preview."}),
        ))


if __name__ == "__main__":
    seed()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8765")))
