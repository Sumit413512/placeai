from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_platform_admin
from app.models import Job, Organization, OrganizationType, RecruiterProfile, User, UserRole
from app.schemas import AdminUserProvision, OrganizationCreate, OrganizationOut, PlatformOverviewOut, UserOut
from app.services import record_audit
from app.access_models import AccessRequest
from app.utils import get_hashed_password

router = APIRouter(prefix="/platform", tags=["Platform Admin"])

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


@router.get("/overview", response_model=PlatformOverviewOut)
def overview(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return PlatformOverviewOut(
        organizations=db.query(Organization).count(),
        students=db.query(User).filter(User.role == UserRole.student).count(),
        recruiters=db.query(User).filter(User.role == UserRole.recruiter).count(),
        institution_admins=db.query(User).filter(User.role == UserRole.institution_admin).count(),
        active_jobs=db.query(Job).filter(Job.is_active.is_(True)).count(),
        applications=sum(len(j.applications) for j in db.query(Job).all()),
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
