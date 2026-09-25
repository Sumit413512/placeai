from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return naive UTC for database DateTime columns without deprecated utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    student = "student"
    recruiter = "recruiter"
    institution_admin = "institution_admin"
    platform_admin = "platform_admin"


class OrganizationType(str, enum.Enum):
    institution = "institution"
    employer = "employer"


class ApplicationStatus(str, enum.Enum):
    applied = "applied"
    shortlisted = "shortlisted"
    interview = "interview"
    offered = "offered"
    rejected = "rejected"
    hired = "hired"
    withdrawn = "withdrawn"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class DriveStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    closed = "closed"
    completed = "completed"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(120), unique=True, index=True, nullable=False)
    organization_type = Column(Enum(OrganizationType), nullable=False, default=OrganizationType.institution)
    domain = Column(String(200), nullable=True)
    website = Column(String(500), nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    country = Column(String(120), default="India")
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(20), default="#5B5BD6")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    users = relationship("User", back_populates="organization")
    students = relationship("StudentProfile", back_populates="institution", foreign_keys="StudentProfile.organization_id")
    drives = relationship("PlacementDrive", back_populates="institution", cascade="all, delete-orphan")
    provisioned_recruiters = relationship("RecruiterProfile", back_populates="provisioning_institution", foreign_keys="RecruiterProfile.provisioned_by_organization_id")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String(320), unique=True, index=True, nullable=False)
    username = Column(String(80), unique=True, index=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    must_change_password = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    reset_token_hash = Column(String(64), nullable=True, index=True)
    reset_token_expires = Column(DateTime, nullable=True)
    auth_version = Column(Integer, nullable=False, default=1)

    organization = relationship("Organization", back_populates="users")
    student_profile = relationship("StudentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    recruiter_profile = relationship("RecruiterProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    jti = Column(String(120), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    auth_version = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class StoredFile(Base):
    __tablename__ = "stored_files"

    id = Column(String, primary_key=True, default=generate_uuid)
    category = Column(String(120), nullable=False, index=True)
    original_filename = Column(String(300), nullable=False)
    mime_type = Column(String(160), nullable=False, default="application/octet-stream")
    size_bytes = Column(Integer, nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    key_hash = Column(String(64), primary_key=True)
    scope = Column(String(80), nullable=False, index=True)
    window_started_at = Column(DateTime, nullable=False, default=utcnow)
    request_count = Column(Integer, nullable=False, default=0)
    blocked_until = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    full_name = Column(String(200), nullable=True)
    college = Column(String(250), nullable=True)
    degree = Column(String(120), nullable=True)
    branch = Column(String(120), nullable=True)
    graduation_year = Column(Integer, nullable=True)
    cgpa = Column(Float, nullable=True)
    bio = Column(Text, nullable=True)
    phone = Column(String(40), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
    skills_json = Column(Text, default="[]")
    desired_roles_json = Column(Text, default="[]")
    ai_summary = Column(Text, nullable=True)
    placement_opt_in = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    tenth_percentage = Column(Float, nullable=True)
    twelfth_percentage = Column(Float, nullable=True)
    diploma_percentage = Column(Float, nullable=True)
    active_backlogs = Column(Integer, default=0)
    historical_backlogs = Column(Integer, default=0)
    academic_gap_months = Column(Integer, default=0)
    work_authorization = Column(String(120), nullable=True)
    certifications_json = Column(Text, default="[]")
    placement_status = Column(String(40), default="unplaced")
    offers_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="student_profile")
    institution = relationship("Organization", back_populates="students", foreign_keys=[organization_id])
    resume = relationship("Resume", back_populates="student", uselist=False, cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="student", cascade="all, delete-orphan")
    mock_interviews = relationship("MockInterview", back_populates="student", cascade="all, delete-orphan")

    @property
    def skills(self):
        try:
            return json.loads(self.skills_json or "[]")
        except json.JSONDecodeError:
            return []

    @skills.setter
    def skills(self, value):
        self.skills_json = json.dumps(value or [])

    @property
    def desired_roles(self):
        try:
            return json.loads(self.desired_roles_json or "[]")
        except json.JSONDecodeError:
            return []

    @desired_roles.setter
    def desired_roles(self, value):
        self.desired_roles_json = json.dumps(value or [])

    @property
    def certifications(self):
        try:
            return json.loads(self.certifications_json or "[]")
        except json.JSONDecodeError:
            return []

    @certifications.setter
    def certifications(self, value):
        self.certifications_json = json.dumps(value or [])


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), unique=True, nullable=False)
    original_filename = Column(String(255), nullable=False)
    filepath = Column(String(700), nullable=False)
    uploaded_at = Column(DateTime, default=utcnow)
    ai_parsed_data_json = Column(Text, nullable=True)
    is_parsed = Column(Boolean, default=False)

    student = relationship("StudentProfile", back_populates="resume")

    @property
    def ai_parsed_data(self):
        if not self.ai_parsed_data_json:
            return None
        try:
            return json.loads(self.ai_parsed_data_json)
        except json.JSONDecodeError:
            return None

    @ai_parsed_data.setter
    def ai_parsed_data(self, value):
        self.ai_parsed_data_json = json.dumps(value) if value else None


class RecruiterProfile(Base):
    __tablename__ = "recruiter_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String(200), nullable=True)
    company_name = Column(String(250), nullable=True)
    company_website = Column(String(500), nullable=True)
    industry = Column(String(150), nullable=True)
    designation = Column(String(150), nullable=True)
    phone = Column(String(40), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    cin = Column(String(40), nullable=True, index=True)
    gstin = Column(String(40), nullable=True, index=True)
    company_address = Column(Text, nullable=True)
    official_email_domain = Column(String(200), nullable=True)
    authorization_letter_path = Column(String(700), nullable=True)
    past_college_relationships_json = Column(Text, default="[]")
    previous_successful_placements = Column(Integer, default=0)
    job_consistency_score = Column(Float, default=0)
    suspicious_domain = Column(Boolean, default=False)
    company_verification_status = Column(String(40), default="manual_review")
    company_verification_confidence = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    provisioned_by_organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="recruiter_profile")
    provisioning_institution = relationship("Organization", back_populates="provisioned_recruiters", foreign_keys=[provisioned_by_organization_id])
    jobs = relationship("Job", back_populates="recruiter", cascade="all, delete-orphan")

    @property
    def past_college_relationships(self):
        try:
            return json.loads(self.past_college_relationships_json or "[]")
        except json.JSONDecodeError:
            return []

    @past_college_relationships.setter
    def past_college_relationships(self, value):
        self.past_college_relationships_json = json.dumps(value or [])


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    recruiter_id = Column(String, ForeignKey("recruiter_profiles.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(200), nullable=True)
    job_type = Column(String(60), default="Full-time")
    salary_range = Column(String(120), nullable=True)
    experience_required = Column(String(120), nullable=True)
    required_skills_json = Column(Text, default="[]")
    preferred_roles_json = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    approval_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.approved, index=True)
    visibility = Column(String(30), default="public")  # public | campus
    target_organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    deadline = Column(DateTime, nullable=True)

    recruiter = relationship("RecruiterProfile", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")
    drives = relationship("PlacementDrive", back_populates="job")
    target_institution = relationship("Organization", foreign_keys=[target_organization_id])

    @property
    def required_skills(self):
        try:
            return json.loads(self.required_skills_json or "[]")
        except json.JSONDecodeError:
            return []

    @required_skills.setter
    def required_skills(self, value):
        self.required_skills_json = json.dumps(value or [])

    @property
    def preferred_roles(self):
        try:
            return json.loads(self.preferred_roles_json or "[]")
        except json.JSONDecodeError:
            return []

    @preferred_roles.setter
    def preferred_roles(self, value):
        self.preferred_roles_json = json.dumps(value or [])


class PlacementDrive(Base):
    __tablename__ = "placement_drives"

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    title = Column(String(250), nullable=False)
    status = Column(Enum(DriveStatus), default=DriveStatus.draft)
    min_cgpa = Column(Float, nullable=True)
    min_tenth_percentage = Column(Float, nullable=True)
    min_twelfth_percentage = Column(Float, nullable=True)
    min_diploma_percentage = Column(Float, nullable=True)
    max_active_backlogs = Column(Integer, nullable=True)
    max_historical_backlogs = Column(Integer, nullable=True)
    max_academic_gap_months = Column(Integer, nullable=True)
    work_authorization_required = Column(String(120), nullable=True)
    allow_placed_students = Column(Boolean, default=True)
    allowed_graduation_years_json = Column(Text, default="[]")
    allowed_branches_json = Column(Text, default="[]")
    required_skills_json = Column(Text, default="[]")
    required_certifications_json = Column(Text, default="[]")
    required_documents_json = Column(Text, default="[]")
    custom_eligibility_rules_json = Column(Text, default="{}")
    registration_deadline = Column(DateTime, nullable=True)
    event_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    institution = relationship("Organization", back_populates="drives")
    job = relationship("Job", back_populates="drives")

    @property
    def allowed_graduation_years(self):
        try:
            return json.loads(self.allowed_graduation_years_json or "[]")
        except json.JSONDecodeError:
            return []

    @allowed_graduation_years.setter
    def allowed_graduation_years(self, value):
        self.allowed_graduation_years_json = json.dumps(value or [])

    @property
    def allowed_branches(self):
        try:
            return json.loads(self.allowed_branches_json or "[]")
        except json.JSONDecodeError:
            return []

    @allowed_branches.setter
    def allowed_branches(self, value):
        self.allowed_branches_json = json.dumps(value or [])

    @property
    def required_skills(self):
        try: return json.loads(self.required_skills_json or "[]")
        except json.JSONDecodeError: return []
    @required_skills.setter
    def required_skills(self, value): self.required_skills_json = json.dumps(value or [])

    @property
    def required_certifications(self):
        try: return json.loads(self.required_certifications_json or "[]")
        except json.JSONDecodeError: return []
    @required_certifications.setter
    def required_certifications(self, value): self.required_certifications_json = json.dumps(value or [])

    @property
    def required_documents(self):
        try: return json.loads(self.required_documents_json or "[]")
        except json.JSONDecodeError: return []
    @required_documents.setter
    def required_documents(self, value): self.required_documents_json = json.dumps(value or [])

    @property
    def custom_eligibility_rules(self):
        try: return json.loads(self.custom_eligibility_rules_json or "{}")
        except json.JSONDecodeError: return {}
    @custom_eligibility_rules.setter
    def custom_eligibility_rules(self, value): self.custom_eligibility_rules_json = json.dumps(value or {})


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("student_id", "job_id", name="uq_student_job_application"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.applied, index=True)
    cover_note = Column(Text, nullable=True)
    ai_match_score = Column(Float, nullable=True)
    ai_match_reasoning = Column(Text, nullable=True)
    recruiter_notes = Column(Text, nullable=True)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=True, index=True)
    pipeline_stage_key = Column(String(120), default="registration", index=True)
    applied_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    student = relationship("StudentProfile", back_populates="applications")
    job = relationship("Job", back_populates="applications")


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    questions_json = Column(Text, nullable=False)
    answers_json = Column(Text, nullable=False)
    evaluation_json = Column(Text, nullable=True)
    overall_score = Column(Integer, nullable=True)
    overall_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    student = relationship("StudentProfile", back_populates="mock_interviews")
    job = relationship("Job")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    action = Column(String(120), nullable=False, index=True)
    entity_type = Column(String(80), nullable=True)
    entity_id = Column(String, nullable=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow, index=True)

    actor = relationship("User")
    organization = relationship("Organization")

    @property
    def details(self):
        try:
            return json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            return {}

    @details.setter
    def details(self, value):
        self.metadata_json = json.dumps(value or {})


# -----------------------------------------------------------------------------
# PlaceAI Enterprise Placement Operations (v3)
# -----------------------------------------------------------------------------

class PlacementAction(Base):
    __tablename__ = "placement_actions"
    __table_args__ = (UniqueConstraint("organization_id", "source_key", name="uq_placement_action_org_source"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=True, index=True)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    action_type = Column(String(80), nullable=False, index=True)
    source_key = Column(String(240), nullable=False)
    title = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, default="medium", index=True)
    status = Column(String(24), nullable=False, default="open", index=True)
    due_at = Column(DateTime, nullable=True, index=True)
    detected_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    resolution_outcome = Column(String(80), nullable=True)
    details_json = Column(Text, nullable=False, default="{}")

    @property
    def details(self):
        try:
            return json.loads(self.details_json or "{}")
        except json.JSONDecodeError:
            return {}

    @details.setter
    def details(self, value):
        self.details_json = json.dumps(value or {})


class DriveStage(Base):
    __tablename__ = "drive_stages"
    __table_args__ = (UniqueConstraint("drive_id", "stage_key", name="uq_drive_stage_key"),)
    id = Column(String, primary_key=True, default=generate_uuid)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=False, index=True)
    stage_key = Column(String(120), nullable=False)
    name = Column(String(180), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    stage_type = Column(String(60), default="custom")
    is_terminal = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class InterviewSchedule(Base):
    __tablename__ = "interview_schedules"
    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=True, index=True)
    round_name = Column(String(180), nullable=False)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    mode = Column(String(40), default="online")
    venue = Column(String(300), nullable=True)
    meeting_url = Column(String(700), nullable=True)
    interviewer = Column(String(200), nullable=True)
    student_slot = Column(String(120), nullable=True)
    instructions = Column(Text, nullable=True)
    status = Column(String(40), default="scheduled", index=True)
    attendance_status = Column(String(40), default="pending")
    result = Column(String(80), nullable=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"
    id = Column(String, primary_key=True, default=generate_uuid)
    interview_id = Column(String, ForeignKey("interview_schedules.id"), nullable=False, unique=True, index=True)
    evaluator_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    technical_knowledge = Column(Integer, nullable=True)
    communication = Column(Integer, nullable=True)
    problem_solving = Column(Integer, nullable=True)
    role_fit = Column(Integer, nullable=True)
    recommendation = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    title = Column(String(220), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(80), default="general", index=True)
    priority = Column(String(30), default="normal", index=True)
    link = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    in_app = Column(Boolean, default=True)
    email = Column(Boolean, default=True)
    whatsapp = Column(Boolean, default=False)
    sms = Column(Boolean, default=False)
    high_priority_only_external = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class InstitutionPolicy(Base):
    __tablename__ = "institution_policies"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    policy_key = Column(String(120), nullable=False, index=True)
    name = Column(String(220), nullable=False)
    description = Column(Text, nullable=True)
    rules_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "policy_key", name="uq_org_policy_key"),)

    @property
    def rules(self):
        try: return json.loads(self.rules_json or "{}")
        except json.JSONDecodeError: return {}
    @rules.setter
    def rules(self, value): self.rules_json = json.dumps(value or {})


class Offer(Base):
    __tablename__ = "offers"
    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False, unique=True, index=True)
    company_name = Column(String(250), nullable=False)
    role = Column(String(220), nullable=False)
    ctc_lpa = Column(Float, nullable=True)
    fixed_pay_lpa = Column(Float, nullable=True)
    variable_pay_lpa = Column(Float, nullable=True)
    location = Column(String(220), nullable=True)
    joining_date = Column(DateTime, nullable=True)
    status = Column(String(40), default="issued", index=True)
    offer_letter_path = Column(String(700), nullable=True)
    bond_terms = Column(Text, nullable=True)
    internship_stipend = Column(Float, nullable=True)
    ppo_status = Column(String(60), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class StudentDocument(Base):
    __tablename__ = "student_documents"
    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    document_type = Column(String(80), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    filepath = Column(String(700), nullable=False)
    visibility = Column(String(40), default="institution_only")
    is_verified = Column(Boolean, default=False)
    uploaded_at = Column(DateTime, default=utcnow)


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=True, index=True)
    title = Column(String(220), nullable=False)
    session_type = Column(String(80), default="placement_drive")
    starts_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)
    token = Column(String(120), unique=True, nullable=False, index=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),)
    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("attendance_sessions.id"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    checked_in_at = Column(DateTime, default=utcnow)
    source = Column(String(40), default="qr")


class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    title = Column(String(240), nullable=False)
    body = Column(Text, nullable=False)
    audience_type = Column(String(80), default="all_students")
    audience_value_json = Column(Text, default="{}")
    priority = Column(String(30), default="normal")
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    @property
    def audience_value(self):
        try: return json.loads(self.audience_value_json or "{}")
        except json.JSONDecodeError: return {}
    @audience_value.setter
    def audience_value(self, value): self.audience_value_json = json.dumps(value or {})


class CommunicationThread(Base):
    __tablename__ = "communication_threads"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    recruiter_profile_id = Column(String, ForeignKey("recruiter_profiles.id"), nullable=True, index=True)
    drive_id = Column(String, ForeignKey("placement_drives.id"), nullable=True, index=True)
    subject = Column(String(240), nullable=False)
    status = Column(String(40), default="open")
    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class CommunicationMessage(Base):
    __tablename__ = "communication_messages"
    id = Column(String, primary_key=True, default=generate_uuid)
    thread_id = Column(String, ForeignKey("communication_threads.id"), nullable=False, index=True)
    sender_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    attachment_path = Column(String(700), nullable=True)
    attachment_filename = Column(String(300), nullable=True)
    attachment_mime = Column(String(120), nullable=True)
    attachment_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class IncidentReport(Base):
    __tablename__ = "incident_reports"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    recruiter_id = Column(String, ForeignKey("recruiter_profiles.id"), nullable=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(40), default="open", index=True)
    confidential = Column(Boolean, default=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class CustomFieldDefinition(Base):
    __tablename__ = "custom_field_definitions"
    id = Column(String, primary_key=True, default=generate_uuid)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    entity_type = Column(String(60), default="student")
    label = Column(String(180), nullable=False)
    field_key = Column(String(120), nullable=False)
    field_type = Column(String(60), default="text")
    required = Column(Boolean, default=False)
    options_json = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "entity_type", "field_key", name="uq_custom_field_key"),)

    @property
    def options(self):
        try: return json.loads(self.options_json or "[]")
        except json.JSONDecodeError: return []
    @options.setter
    def options(self, value): self.options_json = json.dumps(value or [])


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    id = Column(String, primary_key=True, default=generate_uuid)
    definition_id = Column(String, ForeignKey("custom_field_definitions.id"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    value_text = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("definition_id", "student_id", name="uq_custom_field_student"),)


class ProfileChangeRequest(Base):
    __tablename__ = "profile_change_requests"
    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    status = Column(String(40), default="pending", index=True)
    reviewed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)
