from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRoleEnum(str, Enum):
    student = "student"
    recruiter = "recruiter"
    institution_admin = "institution_admin"
    platform_admin = "platform_admin"


class ApplicationStatusEnum(str, Enum):
    applied = "applied"
    shortlisted = "shortlisted"
    interview = "interview"
    offered = "offered"
    rejected = "rejected"
    hired = "hired"
    withdrawn = "withdrawn"


class ApprovalStatusEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class DriveStatusEnum(str, Enum):
    draft = "draft"
    open = "open"
    closed = "closed"
    completed = "completed"


def _strong_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters long")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lowercase letter")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an uppercase letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a number")
    if not any(not c.isalnum() for c in value):
        raise ValueError("Password must contain a symbol")
    return value


class UserAuth(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: UserRoleEnum = UserRoleEnum.student
    organization_slug: Optional[str] = Field(None, max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _strong_password(value)

    @field_validator("username")
    @classmethod
    def username_characters(cls, value: str) -> str:
        value = value.strip()
        if not all(c.isalnum() or c in "._-" for c in value):
            raise ValueError("Username may only contain letters, numbers, dot, underscore, and hyphen")
        return value


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    role: UserRoleEnum
    organization_id: Optional[str] = None
    is_active: bool = True
    email_verified: bool = False
    must_change_password: bool = False

    model_config = {"from_attributes": True}


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 1800


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class LoginJSON(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleAuthRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)
    role: str = Field(default="student", pattern="^(student|recruiter)$")


class StudentProfileCreate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=200)
    college: Optional[str] = Field(None, max_length=250)
    degree: Optional[str] = Field(None, max_length=120)
    branch: Optional[str] = Field(None, max_length=120)
    graduation_year: Optional[int] = Field(None, ge=2020, le=2040)
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    bio: Optional[str] = Field(None, max_length=3000)
    phone: Optional[str] = Field(None, max_length=40)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    github_url: Optional[str] = Field(None, max_length=500)
    portfolio_url: Optional[str] = Field(None, max_length=500)
    skills: Optional[List[str]] = None
    desired_roles: Optional[List[str]] = None
    placement_opt_in: Optional[bool] = None
    tenth_percentage: Optional[float] = Field(None, ge=0, le=100)
    twelfth_percentage: Optional[float] = Field(None, ge=0, le=100)
    diploma_percentage: Optional[float] = Field(None, ge=0, le=100)
    active_backlogs: Optional[int] = Field(None, ge=0, le=100)
    historical_backlogs: Optional[int] = Field(None, ge=0, le=100)
    academic_gap_months: Optional[int] = Field(None, ge=0, le=240)
    work_authorization: Optional[str] = Field(None, max_length=120)
    certifications: Optional[List[str]] = None


class StudentProfileOut(BaseModel):
    id: str
    user_id: str
    organization_id: Optional[str] = None
    full_name: Optional[str] = None
    college: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    cgpa: Optional[float] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    skills: List[str] = []
    desired_roles: List[str] = []
    ai_summary: Optional[str] = None
    has_resume: bool = False
    placement_opt_in: bool = True
    is_verified: bool = False
    tenth_percentage: Optional[float] = None
    twelfth_percentage: Optional[float] = None
    diploma_percentage: Optional[float] = None
    active_backlogs: int = 0
    historical_backlogs: int = 0
    academic_gap_months: int = 0
    work_authorization: Optional[str] = None
    certifications: List[str] = []
    placement_status: str = "unplaced"
    offers_count: int = 0

    model_config = {"from_attributes": True}


class ResumeOut(BaseModel):
    id: str
    original_filename: str
    uploaded_at: datetime
    is_parsed: bool
    ai_parsed_data: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class RecruiterProfileCreate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=200)
    company_name: Optional[str] = Field(None, max_length=250)
    company_website: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=150)
    designation: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=40)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    cin: Optional[str] = Field(None, max_length=40)
    gstin: Optional[str] = Field(None, max_length=40)
    company_address: Optional[str] = Field(None, max_length=2000)
    official_email_domain: Optional[str] = Field(None, max_length=200)
    past_college_relationships: Optional[List[str]] = None
    previous_successful_placements: Optional[int] = Field(None, ge=0)


class RecruiterProfileOut(BaseModel):
    id: str
    user_id: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    industry: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    is_verified: bool = False
    provisioned_by_organization_id: Optional[str] = None
    cin: Optional[str] = None
    gstin: Optional[str] = None
    company_address: Optional[str] = None
    official_email_domain: Optional[str] = None
    past_college_relationships: List[str] = []
    previous_successful_placements: int = 0
    job_consistency_score: float = 0
    suspicious_domain: bool = False
    company_verification_status: str = "manual_review"
    company_verification_confidence: int = 0

    model_config = {"from_attributes": True}




class CompanyTrustCheck(BaseModel):
    key: str
    label: str
    status: str
    detail: str
    weight: int
    earned: int


class CompanyTrustAssessment(BaseModel):
    score: int
    level: str
    label: str
    checks: List[CompanyTrustCheck] = []
    disclaimer: str
    verification_status: str = "Manual Review Required"
    confidence: int = 0
    risk_flags: List[str] = []

class JobCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=20, max_length=12000)
    location: Optional[str] = Field(None, max_length=200)
    job_type: str = Field("Full-time", max_length=60)
    salary_range: Optional[str] = Field(None, max_length=120)
    experience_required: Optional[str] = Field(None, max_length=120)
    required_skills: List[str] = []
    preferred_roles: List[str] = []
    deadline: Optional[datetime] = None
    visibility: str = "public"
    target_organization_slug: Optional[str] = None


class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=20, max_length=12000)
    location: Optional[str] = None
    job_type: Optional[str] = None
    salary_range: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    deadline: Optional[datetime] = None
    visibility: Optional[str] = None
    target_organization_slug: Optional[str] = None


class JobOut(BaseModel):
    id: str
    recruiter_id: str
    title: str
    description: str
    location: Optional[str] = None
    job_type: Optional[str] = None
    salary_range: Optional[str] = None
    experience_required: Optional[str] = None
    required_skills: List[str] = []
    preferred_roles: List[str] = []
    is_active: bool
    approval_status: ApprovalStatusEnum = ApprovalStatusEnum.approved
    visibility: str = "public"
    target_organization_id: Optional[str] = None
    target_organization_name: Optional[str] = None
    created_at: datetime
    deadline: Optional[datetime] = None
    company_name: Optional[str] = None
    application_count: int = 0

    model_config = {"from_attributes": True}


class ApplicationCreate(BaseModel):
    cover_note: Optional[str] = Field(None, max_length=5000)


class StudentBasicOut(BaseModel):
    id: str
    full_name: Optional[str] = None
    college: Optional[str] = None
    cgpa: Optional[float] = None
    skills: List[str] = []
    degree: Optional[str] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: str
    student_id: str
    job_id: str
    status: ApplicationStatusEnum
    cover_note: Optional[str] = None
    ai_match_score: Optional[float] = None
    ai_match_reasoning: Optional[str] = None
    recruiter_notes: Optional[str] = None
    applied_at: datetime
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    job_type: Optional[str] = None
    student: Optional[StudentBasicOut] = None

    model_config = {"from_attributes": True}


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatusEnum
    recruiter_notes: Optional[str] = Field(None, max_length=5000)


class AIResumeParseResult(BaseModel):
    skills: List[str] = []
    experience: List[Dict[str, Any]] = []
    education: List[Dict[str, Any]] = []
    certifications: List[str] = []
    languages: List[str] = []
    summary: Optional[str] = None


class AIRankedCandidate(BaseModel):
    student_id: str
    full_name: Optional[str] = None
    email: str
    college: Optional[str] = None
    cgpa: Optional[float] = None
    skills: List[str]
    ai_match_score: float
    ai_match_reasoning: str


class AIRankResult(BaseModel):
    job_id: str
    job_title: str
    ranked_candidates: List[AIRankedCandidate]


class AIJobMatch(BaseModel):
    job_id: str
    job_title: str
    company_name: Optional[str] = None
    match_score: float
    match_reasoning: str
    missing_skills: List[str] = []


class AIJobMatchResult(BaseModel):
    student_id: str
    recommended_jobs: List[AIJobMatch]


class AISkillGapResult(BaseModel):
    student_id: str
    job_id: str
    job_title: str
    student_skills: List[str]
    required_skills: List[str]
    matching_skills: List[str]
    missing_skills: List[str]
    match_percentage: float
    learning_suggestions: List[Dict[str, str]] = []


class AISummaryResult(BaseModel):
    student_id: str
    summary: str


class InterviewQuestion(BaseModel):
    question_id: int
    question: str


class InterviewQuestionsRequest(BaseModel):
    job_id: str


class InterviewQuestionsResponse(BaseModel):
    job_id: str
    job_title: str
    questions: List[InterviewQuestion]


class AnswerSubmission(BaseModel):
    question_id: int
    question: str
    answer: str


class InterviewEvaluationRequest(BaseModel):
    job_id: str
    answers: List[AnswerSubmission]


class QuestionEvaluation(BaseModel):
    question_id: int
    question: str
    score: int
    feedback: str


class InterviewEvaluationResponse(BaseModel):
    overall_score: int
    overall_feedback: str
    evaluations: List[QuestionEvaluation]


class SkillDistribution(BaseModel):
    skill: str
    count: int


class RecruiterAnalyticsOut(BaseModel):
    total_jobs: int
    total_applications: int
    average_cgpa: Optional[float] = None
    top_skills: List[SkillDistribution] = []


class MockInterviewHistoryOut(BaseModel):
    id: str
    job_title: str
    company_name: Optional[str] = None
    overall_score: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MockInterviewDetailOut(BaseModel):
    id: str
    job_id: str
    job_title: str
    company_name: Optional[str] = None
    questions: List[Any] = []
    answers: List[Any] = []
    evaluations: List[Any] = []
    overall_score: Optional[int] = None
    overall_feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _strong_password(value)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=120)
    domain: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    primary_color: str = "#5B5BD6"

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not all(c.isalnum() or c == "-" for c in value):
            raise ValueError("Slug may contain lowercase letters, numbers, and hyphens")
        return value


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    domain: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: str
    is_active: bool

    model_config = {"from_attributes": True}


class InstitutionDashboardOut(BaseModel):
    organization: OrganizationOut
    total_students: int
    verified_students: int
    active_jobs: int
    open_drives: int
    total_applications: int
    offers: int
    hires: int
    placement_rate: float


class PlacementDriveCreate(BaseModel):
    job_id: str
    title: str = Field(min_length=3, max_length=250)
    min_cgpa: Optional[float] = Field(None, ge=0, le=10)
    min_tenth_percentage: Optional[float] = Field(None, ge=0, le=100)
    min_twelfth_percentage: Optional[float] = Field(None, ge=0, le=100)
    min_diploma_percentage: Optional[float] = Field(None, ge=0, le=100)
    max_active_backlogs: Optional[int] = Field(None, ge=0)
    max_historical_backlogs: Optional[int] = Field(None, ge=0)
    max_academic_gap_months: Optional[int] = Field(None, ge=0)
    work_authorization_required: Optional[str] = None
    allow_placed_students: bool = True
    allowed_graduation_years: List[int] = []
    allowed_branches: List[str] = []
    required_skills: List[str] = []
    required_certifications: List[str] = []
    required_documents: List[str] = []
    custom_eligibility_rules: Dict[str, Any] = {}
    registration_deadline: Optional[datetime] = None
    event_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=5000)
    status: DriveStatusEnum = DriveStatusEnum.draft


class PlacementDriveUpdate(BaseModel):
    title: Optional[str] = None
    min_cgpa: Optional[float] = Field(None, ge=0, le=10)
    min_tenth_percentage: Optional[float] = Field(None, ge=0, le=100)
    min_twelfth_percentage: Optional[float] = Field(None, ge=0, le=100)
    min_diploma_percentage: Optional[float] = Field(None, ge=0, le=100)
    max_active_backlogs: Optional[int] = Field(None, ge=0)
    max_historical_backlogs: Optional[int] = Field(None, ge=0)
    max_academic_gap_months: Optional[int] = Field(None, ge=0)
    work_authorization_required: Optional[str] = None
    allow_placed_students: Optional[bool] = None
    allowed_graduation_years: Optional[List[int]] = None
    allowed_branches: Optional[List[str]] = None
    required_skills: Optional[List[str]] = None
    required_certifications: Optional[List[str]] = None
    required_documents: Optional[List[str]] = None
    custom_eligibility_rules: Optional[Dict[str, Any]] = None
    registration_deadline: Optional[datetime] = None
    event_date: Optional[datetime] = None
    notes: Optional[str] = None
    status: Optional[DriveStatusEnum] = None


class PlacementDriveOut(BaseModel):
    id: str
    organization_id: str
    job_id: str
    title: str
    status: DriveStatusEnum
    min_cgpa: Optional[float] = None
    min_tenth_percentage: Optional[float] = None
    min_twelfth_percentage: Optional[float] = None
    min_diploma_percentage: Optional[float] = None
    max_active_backlogs: Optional[int] = None
    max_historical_backlogs: Optional[int] = None
    max_academic_gap_months: Optional[int] = None
    work_authorization_required: Optional[str] = None
    allow_placed_students: bool = True
    allowed_graduation_years: List[int] = []
    allowed_branches: List[str] = []
    required_skills: List[str] = []
    required_certifications: List[str] = []
    required_documents: List[str] = []
    custom_eligibility_rules: Dict[str, Any] = {}
    registration_deadline: Optional[datetime] = None
    event_date: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    eligible_students: int = 0

    model_config = {"from_attributes": True}


class StudentVerificationUpdate(BaseModel):
    is_verified: bool


class JobApprovalUpdate(BaseModel):
    approval_status: ApprovalStatusEnum


class InstitutionStudentCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=2, max_length=200)
    temporary_password: str = Field(min_length=12, max_length=128)
    degree: Optional[str] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = Field(None, ge=2020, le=2040)
    cgpa: Optional[float] = Field(None, ge=0, le=10)

    @field_validator("temporary_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _strong_password(value)

class AdminUserProvision(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=80)
    full_name: Optional[str] = Field(None, max_length=200)
    temporary_password: str = Field(min_length=12, max_length=128)
    organization_slug: Optional[str] = None
    company_name: Optional[str] = Field(None, max_length=250)

    @field_validator("temporary_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _strong_password(value)


class PlatformOverviewOut(BaseModel):
    organizations: int
    students: int
    recruiters: int
    institution_admins: int
    active_jobs: int
    applications: int
    access_requests: int


class AuditEventOut(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime


class DriveStageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    stage_key: Optional[str] = Field(None, max_length=120)
    order_index: Optional[int] = Field(None, ge=0)
    stage_type: str = "custom"
    is_terminal: bool = False

class InterviewScheduleCreate(BaseModel):
    application_id: str
    drive_id: Optional[str] = None
    round_name: str = Field(min_length=2, max_length=180)
    scheduled_at: datetime
    mode: str = "online"
    venue: Optional[str] = None
    meeting_url: Optional[str] = None
    interviewer: Optional[str] = None
    student_slot: Optional[str] = None
    instructions: Optional[str] = None

class InterviewScheduleUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    mode: Optional[str] = None
    venue: Optional[str] = None
    meeting_url: Optional[str] = None
    interviewer: Optional[str] = None
    student_slot: Optional[str] = None
    instructions: Optional[str] = None
    status: Optional[str] = None
    attendance_status: Optional[str] = None
    result: Optional[str] = None

class InterviewEvaluationCreate(BaseModel):
    technical_knowledge: Optional[int] = Field(None, ge=0, le=10)
    communication: Optional[int] = Field(None, ge=0, le=10)
    problem_solving: Optional[int] = Field(None, ge=0, le=10)
    role_fit: Optional[int] = Field(None, ge=0, le=10)
    recommendation: Optional[str] = None
    notes: Optional[str] = None

class NotificationPreferenceUpdate(BaseModel):
    in_app: bool = True
    email: bool = True
    whatsapp: bool = False
    sms: bool = False
    high_priority_only_external: bool = True

class InstitutionPolicyCreate(BaseModel):
    policy_key: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=220)
    description: Optional[str] = None
    rules: Dict[str, Any] = {}
    is_active: bool = True

class OfferCreate(BaseModel):
    application_id: str
    ctc_lpa: Optional[float] = Field(None, ge=0)
    fixed_pay_lpa: Optional[float] = Field(None, ge=0)
    variable_pay_lpa: Optional[float] = Field(None, ge=0)
    location: Optional[str] = None
    joining_date: Optional[datetime] = None
    status: str = "issued"
    bond_terms: Optional[str] = None
    internship_stipend: Optional[float] = Field(None, ge=0)
    ppo_status: Optional[str] = None

class OfferUpdate(BaseModel):
    status: Optional[str] = None
    ctc_lpa: Optional[float] = Field(None, ge=0)
    fixed_pay_lpa: Optional[float] = Field(None, ge=0)
    variable_pay_lpa: Optional[float] = Field(None, ge=0)
    location: Optional[str] = None
    joining_date: Optional[datetime] = None
    bond_terms: Optional[str] = None
    internship_stipend: Optional[float] = Field(None, ge=0)
    ppo_status: Optional[str] = None

class AttendanceSessionCreate(BaseModel):
    drive_id: Optional[str] = None
    title: str = Field(min_length=2, max_length=220)
    session_type: str = "placement_drive"
    starts_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None

class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    body: str = Field(min_length=2, max_length=10000)
    audience_type: str = "all_students"
    audience_value: Dict[str, Any] = {}
    priority: str = "normal"
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

class CommunicationThreadCreate(BaseModel):
    recruiter_profile_id: Optional[str] = None
    drive_id: Optional[str] = None
    subject: str = Field(min_length=2, max_length=240)

class CommunicationMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10000)

class IncidentReportCreate(BaseModel):
    recruiter_id: Optional[str] = None
    job_id: Optional[str] = None
    category: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=10000)
    confidential: bool = True

class IncidentStatusUpdate(BaseModel):
    status: str
    resolution_notes: Optional[str] = None

class CustomFieldCreate(BaseModel):
    entity_type: str = "student"
    label: str = Field(min_length=2, max_length=180)
    field_key: str = Field(min_length=2, max_length=120)
    field_type: str = "text"
    required: bool = False
    options: List[str] = []

class CustomFieldValueUpdate(BaseModel):
    values: Dict[str, str] = {}

class ProfileChangeReview(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")

class AssistantQuery(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
