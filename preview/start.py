"""Start a disposable, isolated GUI review instance of the existing application."""
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
origin = "https://" + os.environ["RENDER_EXTERNAL_HOSTNAME"]
os.environ.update(
    ENVIRONMENT="test", DATABASE_URL="sqlite:////tmp/placeai-interface-review.db",
    BASE_URL=origin, PUBLIC_APP_URL=origin, ALLOWED_ORIGINS=origin,
    JWT_SECRET_KEY=secrets.token_urlsafe(48), JWT_REFRESH_SECRET_KEY=secrets.token_urlsafe(48),
    AUTO_CREATE_SCHEMA="true", DEV_SHOW_RESET_TOKEN="false",
)
from app.utils import get_hashed_password
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Organization, OrganizationType, User, UserRole, StudentProfile, RecruiterProfile

Base.metadata.create_all(engine)
with SessionLocal.begin() as session:
    org = session.query(Organization).filter_by(slug="review-campus").one_or_none()
    if org is None:
        org = Organization(name="PlaceAI Review Campus", slug="review-campus", organization_type=OrganizationType.institution)
        employer = Organization(name="Campus Review Employer", slug="review-employer", organization_type=OrganizationType.employer)
        session.add_all([org, employer])
        session.flush()
        password_hash = get_hashed_password(os.environ["REVIEW_PASSWORD"], check_breach=False)
        for role in UserRole:
            user = User(email=role.value.replace("_", ".") + "@preview.example.com",
                        username="review_" + role.value, role=role, email_verified=True,
                        hashed_password=password_hash,
                        organization_id={UserRole.platform_admin: None, UserRole.recruiter: employer.id}.get(role, org.id))
            session.add(user)
            session.flush()
            if role == UserRole.student:
                session.add(StudentProfile(user_id=user.id, organization_id=org.id, full_name="Review Student", college=org.name))
            if role == UserRole.recruiter:
                session.add(RecruiterProfile(user_id=user.id, full_name="Review Recruiter", company_name=employer.name, provisioned_by_organization_id=org.id, is_verified=True))
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=int(os.environ["PORT"]))
