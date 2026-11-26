from __future__ import annotations

import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import AccountProtection, StudentProfile, User, UserRole
from app.utils import get_hashed_password

logger = logging.getLogger("placeai.preview_demo")

PREVIEW_DEMO_EMAIL = "preview.student@placeai.in"
PREVIEW_DEMO_PASSWORD = "PlaceAI-Preview#2026!"
PREVIEW_DEMO_USERNAME = "preview_student"


def preview_demo_enabled() -> bool:
    settings = get_settings()
    return (
        settings.running_on_vercel
        and settings.vercel_environment == "preview"
        and not settings.is_production
    )


def seed_preview_demo_account() -> None:
    """Seed a review-only student in isolated Vercel Preview runtimes.

    The preview environment intentionally has no production DATABASE_URL. Every cold
    serverless instance can therefore start with an empty temporary SQLite database.
    Seeding the same review account at startup makes design review deterministic
    without copying production users or institution/recruiter records.
    """
    if not preview_demo_enabled():
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == PREVIEW_DEMO_EMAIL).first()
        password_hash = get_hashed_password(PREVIEW_DEMO_PASSWORD, check_breach=False)
        if user is None:
            user = User(
                email=PREVIEW_DEMO_EMAIL,
                username=PREVIEW_DEMO_USERNAME,
                hashed_password=password_hash,
                role=UserRole.student,
                organization_id=None,
                is_active=True,
                email_verified=True,
                must_change_password=False,
                workspace_guide_pending=False,
            )
            db.add(user)
            db.flush()
        else:
            user.username = PREVIEW_DEMO_USERNAME
            user.hashed_password = password_hash
            user.role = UserRole.student
            user.organization_id = None
            user.is_active = True
            user.email_verified = True
            user.must_change_password = False
            user.workspace_guide_pending = False

        protection = db.get(AccountProtection, user.id)
        if protection is None:
            protection = AccountProtection(
                user_id=user.id,
                verification_required=False,
            )
            db.add(protection)
        else:
            protection.verification_required = False
            protection.mfa_secret = None
            protection.mfa_pending = None
            protection.mfa_pending_expires = None
            protection.challenge_hash = None
            protection.challenge_expires = None
            protection.recovery_hashes = "[]"

        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        if profile is None:
            profile = StudentProfile(user_id=user.id, organization_id=None)
            db.add(profile)

        profile.organization_id = None
        profile.full_name = "PlaceAI Preview Student"
        profile.college = "PlaceAI Preview Campus"
        profile.degree = "B.Tech"
        profile.branch = "Computer Science"
        profile.graduation_year = 2027
        profile.current_semester = 7
        profile.academic_year = "2026–27"
        profile.cgpa = 8.4
        profile.tenth_percentage = 91.0
        profile.twelfth_percentage = 86.0
        profile.active_backlogs = 0
        profile.historical_backlogs = 0
        profile.academic_gap_months = 0
        profile.work_authorization = "India"
        profile.target_role = "Software Engineer"
        profile.skills_json = '["Python","SQL","Data Structures","Web Development"]'
        profile.desired_roles_json = '["Software Engineer","Data Analyst"]'
        profile.certifications_json = '["Preview learning certificate"]'
        profile.bio = (
            "Preview-only student profile for reviewing PlaceAI interface, navigation "
            "and learning-to-placement workflows."
        )
        profile.placement_opt_in = True
        profile.is_verified = True
        profile.placement_status = "unplaced"

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not seed the Vercel Preview demo student")
    finally:
        db.close()
