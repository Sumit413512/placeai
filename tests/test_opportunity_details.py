from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies import require_student
from app.models import (User, UserRole, Organization, StudentProfile, RecruiterProfile,
                        Job, ApprovalStatus, PlacementDrive, DriveStatus, DriveStage, Application)
from app.routers import students


@pytest.fixture
def opportunities():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    db = sessions()
    org = Organization(name="Own institution", slug="own")
    other_org = Organization(name="Other institution", slug="other")
    db.add_all([org, other_org]); db.flush()
    owner = User(email="owner@example.invalid", username="owner", hashed_password="isolated", role=UserRole.student)
    other = User(email="other@example.invalid", username="other", hashed_password="isolated", role=UserRole.student)
    recruiter_user = User(email="recruiter@example.invalid", username="recruiter", hashed_password="isolated", role=UserRole.recruiter)
    db.add_all([owner, other, recruiter_user]); db.flush()
    profile = StudentProfile(user_id=owner.id, organization_id=org.id, full_name="Test student", is_verified=True, cgpa=7.5)
    other_profile = StudentProfile(user_id=other.id, organization_id=other_org.id, is_verified=True, cgpa=8)
    recruiter = RecruiterProfile(user_id=recruiter_user.id, company_name="Actual company", industry="Software", company_website="https://example.com", phone="private-phone", authorization_letter_path="private-file")
    db.add_all([profile, other_profile, recruiter]); db.flush()
    public = Job(recruiter_id=recruiter.id, title="Real public role", description="Published role description", visibility="public", approval_status=ApprovalStatus.approved)
    campus = Job(recruiter_id=recruiter.id, title="Own campus role", description="Campus description", visibility="campus", target_organization_id=org.id, approval_status=ApprovalStatus.approved)
    pending = Job(recruiter_id=recruiter.id, title="Pending", description="Do not expose", visibility="public", approval_status=ApprovalStatus.pending)
    db.add_all([public, campus, pending]); db.flush()
    drive = PlacementDrive(job_id=campus.id, organization_id=org.id, title="Own drive", status=DriveStatus.open, min_cgpa=6.5, max_active_backlogs=0)
    db.add(drive); db.flush(); db.add(DriveStage(drive_id=drive.id, name="Technical interview", stage_key="technical", order_index=1)); db.commit()
    actor = [owner]
    app = FastAPI(); app.include_router(students.router)
    def database():
        with sessions() as session: yield session
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_student] = lambda: actor[0]
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, actor=actor, owner=owner, other=other, profile=profile,
                              public=public, campus=campus, pending=pending, app=app)
    db.close(); engine.dispose()


def test_detail_keeps_institution_and_approval_boundaries(opportunities):
    h = opportunities
    result = h.client.get(f"/students/jobs/{h.campus.id}")
    assert result.status_code == 200
    payload = result.json()
    assert payload["selection_process"] == ["Technical interview"]
    assert {"label": "Minimum CGPA", "value": "6.5"} in payload["criteria"]
    assert {"label": "Maximum active backlogs", "value": "0"} in payload["criteria"]
    assert payload["banner_url"] == "/static/opportunity-workplace.webp"
    assert payload["company"]["website"] == "https://example.com"
    assert "private-phone" not in result.text and "private-file" not in result.text
    h.actor[0] = h.other
    assert h.client.get(f"/students/jobs/{h.campus.id}").status_code == 404
    assert h.client.get(f"/students/jobs/{h.public.id}").status_code == 200
    assert h.client.get(f"/students/jobs/{h.pending.id}").status_code == 404
    h.actor[0] = h.owner; h.profile.is_verified = False; h.db.commit()
    assert h.client.get(f"/students/jobs/{h.campus.id}").status_code == 404


def test_demo_preview_creates_no_jobs_or_applications(opportunities):
    h = opportunities
    before = (h.db.query(Job).count(), h.db.query(Application).count())
    demo = h.client.get('/students/opportunity-demo').json()
    assert demo['is_preview'] and demo['is_demo'] and not demo['can_apply']
    assert 'fictional' in demo['company']['about'].lower()
    assert demo['logo_url'] == '/static/technova-demo.svg'
    assert h.client.post('/students/jobs/technova-demo-preview/apply', json={}).status_code == 404
    assert before == (h.db.query(Job).count(), h.db.query(Application).count())


def test_real_application_flow_and_duplicate_state_are_preserved(opportunities):
    h = opportunities
    assert h.client.get(f'/students/jobs/{h.public.id}').json()['can_apply']
    response = h.client.post(f'/students/jobs/{h.public.id}/apply', json={'cover_note': 'Interested in this published role'})
    assert response.status_code == 201, response.text
    detail = h.client.get(f'/students/jobs/{h.public.id}').json()
    assert detail['already_applied'] and not detail['can_apply']
    assert h.client.post(f'/students/jobs/{h.public.id}/apply', json={}).status_code == 400


def test_anonymous_requests_cannot_read_opportunity_details(opportunities):
    h = opportunities; h.app.dependency_overrides.pop(require_student)
    assert h.client.get(f'/students/jobs/{h.public.id}').status_code in (401, 403)
    assert h.client.get('/students/opportunity-demo').status_code in (401, 403)


def test_application_and_static_production_entries_share_the_new_view():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root/'app/static/app.js').read_bytes() == (root/'public/static/app-core.js').read_bytes()
    assert '__PLACEAI_PRODUCTION_BOOTSTRAP__' in (root/'public/static/app.js').read_text(encoding='utf-8')
    for name in ('opportunities.js', 'opportunities.css', 'opportunity-workplace.webp', 'technova-demo.svg'):
        assert (root/'app/static'/name).read_bytes() == (root/'public/static'/name).read_bytes()
