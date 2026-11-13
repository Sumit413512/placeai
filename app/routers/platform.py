from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import List, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, defer

from app.access_models import AccessRequest
from app.config import get_settings
from app.database import get_db
from app.dependencies import require_platform_admin
from app.email_delivery import send_transactional_email
from app.models import (
    Application,
    ApprovalStatus,
    Job,
    MockInterview,
    LearningNotebook,
    Organization,
    OrganizationType,
    RecruiterProfile,
    RefreshSession,
    Resume,
    User,
    UserRole,
    VideoCourse,
    VideoEnrollment,
    VideoLesson,
    VideoNarration,
)
from app.placement_access import utcnow_naive
from app.schemas import AdminUserProvision, OrganizationCreate, OrganizationOut, PlatformOverviewOut, UserOut
from app.services import create_notification, record_audit
from app.media_delivery import private_media_response
from app.telemetry_models import EmailDeliveryEvent, PageViewEvent
from app.utils import generate_reset_token, get_hashed_password, hash_reset_token

router = APIRouter(prefix="/platform", tags=["Platform Admin"])
settings = get_settings()


class LearningEditorialDecision(BaseModel):
    decision: Literal["approved", "changes_requested"]
    notes: str = Field(default="", max_length=2000)


class LearningRegenerationRequest(BaseModel):
    notes: str = Field(min_length=3, max_length=2000)

_ORG_FIELD_LIMITS = {
    "domain": 200,
    "website": 500,
    "city": 120,
    "state": 120,
    "country": 120,
    "primary_color": 20,
}


def _validate_organization_fields(data: OrganizationCreate) -> None:
    for field, limit in _ORG_FIELD_LIMITS.items():
        value = getattr(data, field, None)
        if value is not None and len(str(value)) > limit:
            raise HTTPException(status_code=422, detail=f"{field} must be {limit} characters or fewer")


def _unique_recruiter_username(email: str, db: Session) -> str:
    local = email.split("@", 1)[0]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", local).strip("._-")[:68]
    if len(base) < 3:
        base = f"recruiter_{base or 'user'}"
    candidate = base
    counter = 1
    while db.query(User).filter(User.username == candidate).first():
        counter += 1
        suffix = f"_{counter}"
        candidate = f"{base[:80-len(suffix)]}{suffix}"
    return candidate


def _record_recruiter_setup_delivery(db: Session, outcome: str, reason: str | None) -> None:
    db.add(EmailDeliveryEvent(purpose="recruiter_setup", outcome=outcome, reason_code=reason))


@router.get("/overview", response_model=PlatformOverviewOut)
def overview(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    now = utcnow_naive()
    active_jobs = db.query(Job).filter(
        Job.is_active.is_(True),
        Job.approval_status == ApprovalStatus.approved,
        or_(Job.deadline.is_(None), Job.deadline > now),
    ).count()
    return PlatformOverviewOut(
        organizations=db.query(Organization).count(),
        students=db.query(User).filter(User.role == UserRole.student).count(),
        recruiters=db.query(User).filter(User.role == UserRole.recruiter).count(),
        institution_admins=db.query(User).filter(User.role == UserRole.institution_admin).count(),
        active_jobs=active_jobs,
        applications=db.query(Application).count(),
        access_requests=db.query(AccessRequest).filter(AccessRequest.status.in_(["new", "under_review", "approved"])).count(),
    )


@router.get("/organizations", response_model=List[OrganizationOut])
def organizations(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return db.query(Organization).order_by(Organization.created_at.desc()).all()


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(data: OrganizationCreate, current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    _validate_organization_fields(data)
    if db.query(Organization).filter(Organization.slug == data.slug).first():
        raise HTTPException(status_code=400, detail="Organization slug already exists")
    org = Organization(
        name=data.name, slug=data.slug, organization_type=OrganizationType.institution,
        domain=data.domain, website=data.website, city=data.city, state=data.state, country=data.country,
        primary_color=data.primary_color,
    )
    db.add(org)
    db.flush()
    record_audit(db, current_user, "platform.organization.created", organization_id=org.id, entity_type="organization", entity_id=org.id, metadata={"name": org.name, "slug": org.slug})
    db.commit()
    db.refresh(org)
    return org


@router.post("/institution-admins", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def provision_institution_admin(data: AdminUserProvision, current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    if not data.organization_slug:
        raise HTTPException(status_code=400, detail="organization_slug is required")
    org = db.query(Organization).filter(Organization.slug == data.organization_slug.lower(), Organization.is_active.is_(True)).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if db.query(User).filter((User.email == data.email.lower()) | (User.username == data.username)).first():
        raise HTTPException(status_code=400, detail="Email or username already exists")
    user = User(email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password), role=UserRole.institution_admin, organization_id=org.id, must_change_password=True)
    db.add(user)
    db.flush()
    record_audit(db, current_user, "platform.institution_admin.provisioned", organization_id=org.id, entity_type="user", entity_id=user.id, metadata={"email": user.email})
    db.commit()
    db.refresh(user)
    return user


@router.post("/recruiters", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def provision_recruiter(data: AdminUserProvision, current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    if db.query(User).filter((User.email == data.email.lower()) | (User.username == data.username)).first():
        raise HTTPException(status_code=400, detail="Email or username already exists")
    provisioned_org = None
    if data.organization_slug:
        provisioned_org = db.query(Organization).filter(Organization.slug == data.organization_slug.lower(), Organization.is_active.is_(True)).first()
        if not provisioned_org:
            raise HTTPException(status_code=404, detail="Organization not found")
    user = User(email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter, must_change_password=True)
    db.add(user)
    db.flush()
    profile = RecruiterProfile(
        user_id=user.id, full_name=data.full_name, company_name=data.company_name, is_verified=True,
        provisioned_by_organization_id=provisioned_org.id if provisioned_org else None,
    )
    db.add(profile)
    db.flush()
    record_audit(db, current_user, "platform.recruiter.provisioned", organization_id=provisioned_org.id if provisioned_org else None, entity_type="recruiter_profile", entity_id=profile.id, metadata={"email": user.email, "company": data.company_name})
    db.commit()
    db.refresh(user)
    return user


@router.post("/access-requests/{request_id}/provision-recruiter")
def provision_recruiter_from_access_request(
    request_id: str,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Turn an approved recruiter request into a real account with an emailed password-setup link.

    Platform Admin never chooses or sees a permanent password. The new account starts
    with an inaccessible random secret and becomes usable only after the recruiter uses
    the one-time setup link sent to the approved work email address.
    """
    item = db.query(AccessRequest).filter(AccessRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Access request not found")
    if item.requested_role != "recruiter":
        raise HTTPException(status_code=422, detail="Only recruiter access requests can use this provisioning action")
    if item.status not in {"approved", "provisioned"}:
        raise HTTPException(status_code=409, detail="Approve the recruiter access request before provisioning the account")

    email = item.work_email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    account_created = False
    if user:
        if user.role != UserRole.recruiter:
            raise HTTPException(status_code=409, detail="This email already belongs to a different PlaceAI account role")
        if not user.is_active:
            raise HTTPException(status_code=409, detail="The existing recruiter account is inactive and must be reviewed before access can be restored")
    else:
        user = User(
            email=email,
            username=_unique_recruiter_username(email, db),
            hashed_password=get_hashed_password(generate_reset_token()),
            role=UserRole.recruiter,
            email_verified=False,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        account_created = True

    profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).first()
    if not profile:
        profile = RecruiterProfile(
            user_id=user.id,
            full_name=item.full_name,
            company_name=item.organization_name,
            is_verified=True,
        )
        db.add(profile)
        db.flush()
    else:
        if not profile.full_name and item.full_name:
            profile.full_name = item.full_name
        if not profile.company_name and item.organization_name:
            profile.company_name = item.organization_name
        profile.is_verified = True

    setup_token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(setup_token)
    user.reset_token_expires = utcnow_naive() + timedelta(minutes=30)
    db.commit()

    setup_link = f"{settings.base_url}/?reset_token={setup_token}"
    outcome, reason = send_transactional_email(
        settings,
        recipient=email,
        subject="Set up your PlaceAI Recruiter password",
        body=(
            f"Hello {item.full_name},\n\n"
            "Your PlaceAI Recruiter access request has been approved and your recruiter account is ready for setup.\n\n"
            "Choose your own password using this one-time link. It expires in 30 minutes:\n\n"
            f"{setup_link}\n\n"
            "No administrator knows or needs to set your permanent password. If you did not request recruiter access, do not use this link and contact the PlaceAI administrator.\n"
        ),
    )

    if outcome == "sent":
        item.status = "provisioned"
        item.reviewed_by_user_id = current_user.id
        item.updated_at = utcnow_naive()
    else:
        user.reset_token_hash = None
        user.reset_token_expires = None
        if item.status != "provisioned":
            item.status = "approved"

    _record_recruiter_setup_delivery(db, outcome, reason)
    record_audit(
        db,
        current_user,
        "platform.recruiter.access_request_provisioned",
        entity_type="user",
        entity_id=user.id,
        metadata={
            "access_request_id": item.id,
            "account_created": account_created,
            "setup_email_sent": outcome == "sent",
        },
    )
    db.commit()
    db.refresh(user)
    db.refresh(item)

    return {
        "request_id": item.id,
        "status": item.status,
        "account_created": account_created,
        "setup_email_sent": outcome == "sent",
        "email": user.email,
        "username": user.username,
        "message": (
            "Recruiter account provisioned and a one-time password setup link was sent."
            if outcome == "sent"
            else "Recruiter account exists, but the password setup email could not be delivered. Retry this action after email delivery is healthy."
        ),
    }


def _platform_registration_item(db: Session, user: User, *, detailed: bool = False) -> dict:
    now = utcnow_naive()
    organization = user.organization
    student = user.student_profile
    recruiter = user.recruiter_profile
    display_name = (
        (student.full_name if student else None)
        or (recruiter.full_name if recruiter else None)
        or user.username
        or user.email
    )
    organization_name = (
        organization.name if organization else
        (student.college if student and student.college else None)
    )
    if recruiter and recruiter.company_name:
        organization_name = recruiter.company_name

    active_sessions = (
        db.query(RefreshSession)
        .filter(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .count()
    )

    activity = {
        "active_sessions": active_sessions,
        "mock_interview_attempts": 0,
        "mock_interviews_evaluated": 0,
        "last_mock_interview_at": None,
        "last_mock_score": None,
        "applications": 0,
        "resume_uploaded": False,
        "resume_parsed": False,
        "resume_uploaded_at": None,
        "jobs_created": 0,
    }

    profile: dict = {}
    if student:
        mock_query = db.query(MockInterview).filter(MockInterview.student_id == student.id)
        latest_mock = mock_query.order_by(MockInterview.created_at.desc()).first()
        resume = db.query(Resume).filter(Resume.student_id == student.id).first()
        activity.update(
            {
                "mock_interview_attempts": mock_query.count(),
                "mock_interviews_evaluated": mock_query.filter(MockInterview.overall_score.isnot(None)).count(),
                "last_mock_interview_at": latest_mock.created_at if latest_mock else None,
                "last_mock_score": latest_mock.overall_score if latest_mock else None,
                "applications": db.query(Application).filter(Application.student_id == student.id).count(),
                "resume_uploaded": bool(resume),
                "resume_parsed": bool(resume and resume.is_parsed),
                "resume_uploaded_at": resume.uploaded_at if resume else None,
            }
        )
        if detailed:
            profile = {
                "profile_type": "student",
                "phone": student.phone,
                "college": student.college,
                "degree": student.degree,
                "branch": student.branch,
                "graduation_year": student.graduation_year,
                "cgpa": student.cgpa,
                "skills": student.skills,
                "desired_roles": student.desired_roles,
                "placement_status": student.placement_status,
                "placement_opt_in": student.placement_opt_in,
                "is_verified": student.is_verified,
                "tenth_percentage": student.tenth_percentage,
                "twelfth_percentage": student.twelfth_percentage,
                "active_backlogs": student.active_backlogs,
                "historical_backlogs": student.historical_backlogs,
                "linkedin_url": student.linkedin_url,
                "github_url": student.github_url,
                "portfolio_url": student.portfolio_url,
            }
    elif recruiter:
        activity["jobs_created"] = db.query(Job).filter(Job.recruiter_id == recruiter.id).count()
        if detailed:
            profile = {
                "profile_type": "recruiter",
                "phone": recruiter.phone,
                "company_name": recruiter.company_name,
                "company_website": recruiter.company_website,
                "industry": recruiter.industry,
                "designation": recruiter.designation,
                "linkedin_url": recruiter.linkedin_url,
                "is_verified": recruiter.is_verified,
                "verification_status": recruiter.company_verification_status,
                "verification_confidence": recruiter.company_verification_confidence,
                "official_email_domain": recruiter.official_email_domain,
            }
    elif detailed and organization:
        profile = {
            "profile_type": "institution_admin",
            "organization_name": organization.name,
            "organization_slug": organization.slug,
            "domain": organization.domain,
            "website": organization.website,
            "city": organization.city,
            "state": organization.state,
            "country": organization.country,
            "organization_active": organization.is_active,
        }

    item = {
        "id": user.id,
        "name": display_name,
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
        "organization": organization_name,
        "is_active": bool(user.is_active),
        "email_verified": bool(user.email_verified),
        "registered_at": user.created_at,
        "last_login_at": user.last_login_at,
        "activity": activity,
    }
    if detailed:
        item["profile"] = profile
        item["security_note"] = (
            "Passwords, password hashes, reset tokens, refresh-token identifiers and other authentication secrets "
            "are intentionally never exposed in Platform Admin."
        )
    return item


@router.get("/registrations")
def platform_registrations(
    role: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    allowed_roles = {item.value for item in UserRole}
    if role and role not in allowed_roles:
        raise HTTPException(status_code=422, detail="Unknown account role")

    query = db.query(User)
    if role:
        query = query.filter(User.role == UserRole(role))
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    counts = {
        value: db.query(User).filter(User.role == UserRole(value)).count()
        for value in sorted(allowed_roles)
    }
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "summary": {
            "all_accounts": db.query(User).count(),
            "students": counts.get("student", 0),
            "recruiters": counts.get("recruiter", 0),
            "institution_admins": counts.get("institution_admin", 0),
            "platform_admins": counts.get("platform_admin", 0),
        },
        "items": [_platform_registration_item(db, user) for user in users],
    }


@router.get("/registrations/{user_id}")
def platform_registration_detail(
    user_id: str,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    return _platform_registration_item(db, user, detailed=True)


@router.get("/engagement")
def platform_engagement(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    now = utcnow_naive()
    since = now - timedelta(days=days)
    page_filter = PageViewEvent.created_at >= since

    page_views = db.query(PageViewEvent).filter(page_filter).count()
    unique_visitors = (
        db.query(func.count(func.distinct(PageViewEvent.visitor_hash)))
        .filter(page_filter)
        .scalar()
        or 0
    )
    signed_in_users = (
        db.query(func.count(func.distinct(PageViewEvent.user_id)))
        .filter(page_filter, PageViewEvent.user_id.isnot(None))
        .scalar()
        or 0
    )
    tracking_since = db.query(func.min(PageViewEvent.created_at)).scalar()

    top_pages = [
        {"path": path, "views": views, "visitors": visitors}
        for path, views, visitors in (
            db.query(
                PageViewEvent.path,
                func.count(PageViewEvent.id),
                func.count(func.distinct(PageViewEvent.visitor_hash)),
            )
            .filter(page_filter)
            .group_by(PageViewEvent.path)
            .order_by(func.count(PageViewEvent.id).desc())
            .limit(20)
            .all()
        )
    ]

    daily = [
        {"date": str(day), "views": views, "visitors": visitors}
        for day, views, visitors in (
            db.query(
                func.date(PageViewEvent.created_at),
                func.count(PageViewEvent.id),
                func.count(func.distinct(PageViewEvent.visitor_hash)),
            )
            .filter(page_filter)
            .group_by(func.date(PageViewEvent.created_at))
            .order_by(func.date(PageViewEvent.created_at).asc())
            .all()
        )
    ]

    referrers = [
        {"host": host or "Direct / unavailable", "views": views}
        for host, views in (
            db.query(PageViewEvent.referrer_host, func.count(PageViewEvent.id))
            .filter(page_filter)
            .group_by(PageViewEvent.referrer_host)
            .order_by(func.count(PageViewEvent.id).desc())
            .limit(10)
            .all()
        )
    ]

    active_roles = {
        role.value: count
        for role, count in (
            db.query(User.role, func.count(User.id))
            .filter(User.last_login_at.isnot(None), User.last_login_at >= since)
            .group_by(User.role)
            .all()
        )
    }

    return {
        "days": days,
        "tracking_since": tracking_since,
        "summary": {
            "page_views": page_views,
            "unique_visitors": unique_visitors,
            "signed_in_users_seen": signed_in_users,
            "registrations": db.query(User).filter(User.created_at >= since).count(),
            "students_active": active_roles.get("student", 0),
            "recruiters_active": active_roles.get("recruiter", 0),
            "institution_admins_active": active_roles.get("institution_admin", 0),
            "mock_interviews": db.query(MockInterview).filter(MockInterview.created_at >= since).count(),
            "applications": db.query(Application).filter(Application.applied_at >= since).count(),
            "resumes_uploaded": db.query(Resume).filter(Resume.uploaded_at >= since).count(),
        },
        "top_pages": top_pages,
        "daily": daily,
        "referrers": referrers,
        "note": (
            "Page-view history starts when PlaceAI first-party telemetry is deployed. "
            "Historical visitors from before that release cannot be reconstructed."
        ),
    }


@router.get("/processing-recovery")
def processing_recovery_status(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    from app.processing_recovery import overview
    return overview(db)


@router.post("/processing-recovery/{kind}/{identifier}/retry")
def retry_processing(kind: str, identifier: str, request: Request, tasks: BackgroundTasks,
                     current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    if kind not in {"courses", "notes", "assessments"}:
        raise HTTPException(404, "Recovery category not found")
    if not current_user.last_login_at or current_user.last_login_at < utcnow_naive()-timedelta(minutes=15):
        raise HTTPException(403, "Sign out and sign in again before requesting a processing repair.")
    from app.rate_limit import enforce_rate_limit
    enforce_rate_limit(db, request, scope="processing-recovery", limit=12, window_seconds=3600, block_seconds=600)
    from app.processing_recovery import recover
    from app.routers.learning_hub import wake_worker
    result = recover(db, current_user, kind, identifier)
    tasks.add_task(wake_worker)
    return result


def _editorial_item(kind: str, row, *, parent_title: str | None = None):
    return {
        "kind": kind,
        "id": row.id,
        "title": row.title,
        "parent_title": parent_title,
        "generation_status": row.state,
        "editorial_status": row.editorial_status,
        "editorial_notes": row.editorial_notes,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/learning-content-review")
def learning_content_review(current_user: User = Depends(require_platform_admin),
                            db: Session = Depends(get_db)):
    review_states = ("pending_review", "changes_requested")
    notes = db.query(LearningNotebook).filter(
        LearningNotebook.editorial_status.in_(review_states)).order_by(
        LearningNotebook.updated_at.asc()).limit(100).all()
    courses = db.query(VideoCourse).filter(
        VideoCourse.editorial_status.in_(review_states)).order_by(
        VideoCourse.updated_at.asc()).limit(100).all()
    lesson_rows = db.query(VideoLesson, VideoCourse.title).options(
        defer(VideoLesson.video_data)).join(
        VideoCourse, VideoCourse.id == VideoLesson.course_id).filter(
        VideoLesson.editorial_status.in_(review_states),
        ~VideoCourse.editorial_status.in_(review_states)).order_by(
        VideoLesson.updated_at.asc()).limit(200).all()
    # Course state=ready means its SYLLABUS passed, not that MP4s exist.
    # Never report "check required / passed" prematurely or load video BLOBs.
    from collections import defaultdict
    from app.learning_publication import checks_passed
    course_items = {row.id: _editorial_item("course", row) for row in courses}
    if course_items:
        ids = list(course_items)
        raw_lessons = db.query(
            VideoLesson.id, VideoLesson.course_id, VideoLesson.state,
            VideoLesson.error_code
        ).filter(VideoLesson.course_id.in_(ids)).all()
        media_ids = {lesson_id for lesson_id, in db.query(VideoLesson.id).filter(
            VideoLesson.course_id.in_(ids), VideoLesson.video_data.is_not(None)).all()}
        checked_ids = {lesson_id for lesson_id, body in db.query(
            VideoLesson.id, VideoLesson.content_json).filter(
            VideoLesson.course_id.in_(ids), VideoLesson.state == "ready",
            VideoLesson.video_data.is_not(None)).all()
            if checks_passed(json.loads(body))}
        grouped = defaultdict(list)
        for record in raw_lessons:
            grouped[record.course_id].append(record)
        for course in courses:
            lessons = grouped[course.id]
            expected = len(json.loads(course.plan_json).get("lessons", []))
            ready = sum(lesson.state == "ready" and lesson.id in media_ids for lesson in lessons)
            checked = sum(lesson.id in checked_ids for lesson in lessons)
            failed = sum(lesson.state == "failed" for lesson in lessons)
            author_waiting = sum(lesson.error_code == "AUTHOR_CAPACITY" and
                                 lesson.state == "retrying" for lesson in lessons)
            complete = (course.state == "ready" and expected > 0 and
                        len(lessons) == expected and ready == checked == expected)
            item = course_items[course.id]
            item.update(planned_count=expected, ready_count=ready,
                        checked_count=checked, failed_count=failed,
                        author_waiting_count=author_waiting,
                        review_ready=complete,
                        preparation_stage=("review_ready" if complete else
                            "repair_required" if failed else
                            "waiting_ai_capacity" if author_waiting else
                            "generating_videos"))
    items = ([_editorial_item("notes", row) for row in notes]
             + [course_items[row.id] for row in courses]
             + [_editorial_item("lesson", row, parent_title=course_title)
                for row, course_title in lesson_rows])
    items.sort(key=lambda item: item["updated_at"])
    return {"items": items, "pending_count": sum(
        item["editorial_status"] == "pending_review"
        and (item["kind"] != "course" or item["review_ready"]) for item in items),
        "preparing_count": sum(item["kind"] == "course" and not item["review_ready"]
                               for item in items)}


@router.get("/learning-content-review/{kind}/{identifier}")
def preview_learning_content(kind: str, identifier: str,
                             current_user: User = Depends(require_platform_admin),
                             db: Session = Depends(get_db)):
    if kind == "notes":
        row = db.get(LearningNotebook, identifier)
        if not row:
            raise HTTPException(404, "Learning notebook not found")
        return {**_editorial_item(kind, row), "plan": json.loads(row.plan_json),
                "chapters": json.loads(row.chapters_json), "sources": json.loads(row.sources_json)}
    if kind == "course":
        row = db.get(VideoCourse, identifier)
        if not row:
            raise HTTPException(404, "Video course not found")
        # Never hydrate every MP4 BLOB while opening a course review. A complete
        # course can contain dozens of videos and exhaust the web process.
        lessons = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(
            course_id=row.id).order_by(VideoLesson.position).all()
        media_ids = {lesson_id for lesson_id, in db.query(VideoLesson.id).filter(
            VideoLesson.course_id == row.id, VideoLesson.video_data.is_not(None)).all()}
        plan = json.loads(row.plan_json)
        return {**_editorial_item(kind, row), "plan": plan,
                "sources": json.loads(row.sources_json),
                "planned_count": len(plan.get("lessons", [])),
                "ready_count": sum(lesson.state == "ready" and lesson.id in media_ids for lesson in lessons),
                "lessons": [{**_editorial_item("lesson", lesson, parent_title=row.title),
                             "position": lesson.position,
                             "duration_seconds": lesson.duration_seconds,
                             "media_available": lesson.id in media_ids,
                             "content": json.loads(lesson.content_json)} for lesson in lessons]}
    if kind == "lesson":
        row = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(id=identifier).first()
        if not row:
            raise HTTPException(404, "Video lesson not found")
        course = db.get(VideoCourse, row.course_id)
        return {**_editorial_item(kind, row, parent_title=course.title if course else None),
                "duration_seconds": row.duration_seconds, "content": json.loads(row.content_json),
                "media_available": db.query(VideoLesson.id).filter(
                    VideoLesson.id == row.id, VideoLesson.video_data.is_not(None)).first() is not None}
    raise HTTPException(404, "Learning content type not found")


@router.get("/learning-content-review/lesson/{identifier}/media")
def preview_learning_video(identifier: str, request: Request,
                           current_user: User = Depends(require_platform_admin),
                           db: Session = Depends(get_db)):
    row = db.get(VideoLesson, identifier)
    if not row or not row.video_data:
        raise HTTPException(404, "Video preview is not available")
    return private_media_response(row.video_data, request)


@router.patch("/learning-content-review/{kind}/{identifier}")
def review_learning_content(kind: str, identifier: str, body: LearningEditorialDecision,
                            current_user: User = Depends(require_platform_admin),
                            db: Session = Depends(get_db)):
    model = {"notes": LearningNotebook, "course": VideoCourse, "lesson": VideoLesson}.get(kind)
    if not model:
        raise HTTPException(404, "Learning content type not found")
    query = db.query(model)
    if kind == "lesson":
        query = query.options(defer(VideoLesson.video_data))
    row = query.filter_by(id=identifier).with_for_update().first()
    if not row:
        raise HTTPException(404, "Learning content not found")
    if row.state != "ready":
        raise HTTPException(409, "Only fully generated content can be reviewed")
    if body.decision == "changes_requested" and not body.notes.strip():
        raise HTTPException(422, "Explain the changes needed before sending it back")
    if kind == "lesson" and body.decision == "approved":
        from app.learning_publication import checks_passed
        has_media = db.query(VideoLesson.id).filter(
            VideoLesson.id == row.id, VideoLesson.video_data.is_not(None)).first() is not None
        if not has_media or not checks_passed(json.loads(row.content_json)):
            raise HTTPException(409, "The lesson video and all automated quality checks must pass before approval")
    prior_status = row.editorial_status
    if kind == "course":
        lessons = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(
            course_id=row.id).order_by(VideoLesson.position).all()
        expected = len(json.loads(row.plan_json).get("lessons", []))
        if body.decision == "approved":
            from app.learning_publication import checks_passed
            media_ids = {lesson_id for lesson_id, in db.query(VideoLesson.id).filter(
                VideoLesson.course_id == row.id, VideoLesson.video_data.is_not(None)).all()}
            if not lessons or len(lessons) != expected or any(
                lesson.state != "ready" or lesson.id not in media_ids
                or not checks_passed(json.loads(lesson.content_json))
                for lesson in lessons
            ):
                raise HTTPException(409, "Every planned lesson, video and quality check must be ready before approval")
        for lesson in lessons:
            if lesson.state == "ready":
                lesson.editorial_status = body.decision
                lesson.editorial_notes = body.notes.strip()
                lesson.reviewed_by_user_id = current_user.id
                lesson.reviewed_at = utcnow_naive()
    row.editorial_status = body.decision
    row.editorial_notes = body.notes.strip()
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = utcnow_naive()
    record_audit(db, current_user, f"learning.{kind}.{body.decision}",
                 entity_type=f"learning_{kind}", entity_id=row.id,
                 metadata={"notes_supplied": bool(row.editorial_notes)})
    if kind == "course" and body.decision == "approved" and prior_status != "approved":
        learner_ids = {user_id for user_id, in db.query(VideoEnrollment.user_id).filter_by(course_id=row.id)}
        if row.shared_key is None and row.user_id:
            learner_ids.add(row.user_id)
        for learner_id in learner_ids:
            create_notification(db, learner_id, "Your video course is ready",
                f"{row.title} passed the full course review and is ready to begin.",
                category="learning", priority="high", link="learning-hub")
    db.commit()
    return _editorial_item(kind, row)


@router.post("/learning-content-review/lesson/{identifier}/regenerate", status_code=202)
def regenerate_learning_video(identifier: str, body: LearningRegenerationRequest,
                              tasks: BackgroundTasks,
                              current_user: User = Depends(require_platform_admin),
                              db: Session = Depends(get_db)):
    row = db.query(VideoLesson).filter_by(id=identifier).with_for_update().first()
    if not row:
        raise HTTPException(404, "Video lesson not found")
    course = db.query(VideoCourse).filter_by(id=row.course_id).with_for_update().first()
    content = json.loads(row.content_json or "{}")
    findings = [body.notes.strip()]
    for check in ("content_review", "media_review", "audiovisual_review"):
        report = content.get(check, {})
        if report and report.get("passed") is not True:
            findings.append(f"Automated {check.replace('_', ' ')} did not pass; correct its reported defects.")
    db.query(VideoNarration).filter_by(lesson_id=row.id).delete(synchronize_session=False)
    row.state = "queued"
    row.content_json = json.dumps({"revision_feedback": findings})
    row.video_data = None
    row.duration_seconds = 0
    row.attempts = 0
    row.error_code = None
    row.lease_token = None
    row.lease_until = None
    row.available_at = utcnow_naive()
    row.editorial_status = "generating"
    row.editorial_notes = body.notes.strip()
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = utcnow_naive()
    if course:
        course.editorial_status = "pending_review"
        course.editorial_notes = "One or more lessons are being regenerated after review."
        course.reviewed_by_user_id = current_user.id
        course.reviewed_at = utcnow_naive()
    record_audit(db, current_user, "learning.lesson.regeneration_requested",
                 entity_type="learning_lesson", entity_id=row.id,
                 metadata={"course_id": row.course_id, "findings": len(findings)})
    db.commit()
    from app.routers.learning_hub import wake_worker
    tasks.add_task(wake_worker)
    return {"id": row.id, "status": row.state,
            "message": "The lesson is queued for corrected regeneration and full automated rechecking."}
