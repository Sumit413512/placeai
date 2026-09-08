from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_platform_admin
from app.models import DemoRequest, Job, Organization, OrganizationType, RecruiterProfile, StudentProfile, User, UserRole
from app.schemas import AdminUserProvision, DemoRequestOut, DemoRequestStatusUpdate, OrganizationCreate, OrganizationOut, PlatformOverviewOut, UserOut
from app.services import record_audit
from app.utils import get_hashed_password

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


@router.get("/overview", response_model=PlatformOverviewOut)
def overview(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return PlatformOverviewOut(
        organizations=db.query(Organization).count(),
        students=db.query(User).filter(User.role == UserRole.student).count(),
        recruiters=db.query(User).filter(User.role == UserRole.recruiter).count(),
        institution_admins=db.query(User).filter(User.role == UserRole.institution_admin).count(),
        active_jobs=db.query(Job).filter(Job.is_active.is_(True)).count(),
        applications=sum(len(j.applications) for j in db.query(Job).all()),
        demo_requests=db.query(DemoRequest).filter(DemoRequest.status != "lost").count(),
    )


@router.get("/organizations", response_model=List[OrganizationOut])
def organizations(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return db.query(Organization).order_by(Organization.created_at.desc()).all()


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(data: OrganizationCreate, current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
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
    org = db.query(Organization).filter(Organization.slug == data.organization_slug.lower()).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if db.query(User).filter((User.email == data.email.lower()) | (User.username == data.username)).first():
        raise HTTPException(status_code=400, detail="Email or username already exists")
    user = User(email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password), role=UserRole.institution_admin, organization_id=org.id)
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
    user = User(email=data.email.lower(), username=data.username, hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter)
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


@router.get("/demo-requests", response_model=List[DemoRequestOut])
def demo_requests(current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return db.query(DemoRequest).order_by(DemoRequest.created_at.desc()).limit(1000).all()


@router.patch("/demo-requests/{request_id}", response_model=DemoRequestOut)
def update_demo_request(request_id: str, data: DemoRequestStatusUpdate, current_user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    lead = db.query(DemoRequest).filter(DemoRequest.id == request_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Demo request not found")
    lead.status = data.status
    record_audit(db, current_user, "platform.demo_request.status_changed", entity_type="demo_request", entity_id=lead.id, metadata={"status": lead.status})
    db.commit()
    db.refresh(lead)
    return lead
