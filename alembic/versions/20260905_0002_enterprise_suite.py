"""PlaceAI 3.0 enterprise placement operations.

Revision ID: 20260905_0002
Revises: 20260904_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.database import Base
from app import models  # noqa: F401

revision = "20260905_0002"
down_revision = "20260904_0001"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()


def _add(table: str, *columns: sa.Column) -> None:
    existing = _column_names(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)
            existing.add(column.name)


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    inspector = inspect(op.get_bind())
    existing = {idx.get("name") for idx in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=False)


def _ensure_fk(table: str, name: str, referred_table: str, local_cols: list[str], remote_cols: list[str]) -> None:
    inspector = inspect(op.get_bind())
    fks = inspector.get_foreign_keys(table)
    for fk in fks:
        if fk.get("name") == name or (fk.get("referred_table") == referred_table and fk.get("constrained_columns") == local_cols):
            return
    # SQLite cannot ALTER ADD CONSTRAINT; fresh SQLite databases already receive this
    # FK from the metadata-driven baseline, while production PostgreSQL can add it.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(name, table, referred_table, local_cols, remote_cols)


def upgrade() -> None:
    _add("student_profiles",
        sa.Column("tenth_percentage", sa.Float(), nullable=True),
        sa.Column("twelfth_percentage", sa.Float(), nullable=True),
        sa.Column("diploma_percentage", sa.Float(), nullable=True),
        sa.Column("active_backlogs", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("historical_backlogs", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("academic_gap_months", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("work_authorization", sa.String(length=120), nullable=True),
        sa.Column("certifications_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("placement_status", sa.String(length=40), nullable=True, server_default="unplaced"),
        sa.Column("offers_count", sa.Integer(), nullable=True, server_default="0"),
    )
    _add("recruiter_profiles",
        sa.Column("cin", sa.String(length=40), nullable=True),
        sa.Column("gstin", sa.String(length=40), nullable=True),
        sa.Column("company_address", sa.Text(), nullable=True),
        sa.Column("official_email_domain", sa.String(length=200), nullable=True),
        sa.Column("authorization_letter_path", sa.String(length=700), nullable=True),
        sa.Column("past_college_relationships_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("previous_successful_placements", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("job_consistency_score", sa.Float(), nullable=True, server_default="0"),
        sa.Column("suspicious_domain", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("company_verification_status", sa.String(length=40), nullable=True, server_default="manual_review"),
        sa.Column("company_verification_confidence", sa.Integer(), nullable=True, server_default="0"),
    )
    _add("placement_drives",
        sa.Column("min_tenth_percentage", sa.Float(), nullable=True),
        sa.Column("min_twelfth_percentage", sa.Float(), nullable=True),
        sa.Column("min_diploma_percentage", sa.Float(), nullable=True),
        sa.Column("max_active_backlogs", sa.Integer(), nullable=True),
        sa.Column("max_historical_backlogs", sa.Integer(), nullable=True),
        sa.Column("max_academic_gap_months", sa.Integer(), nullable=True),
        sa.Column("work_authorization_required", sa.String(length=120), nullable=True),
        sa.Column("allow_placed_students", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column("required_skills_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("required_certifications_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("required_documents_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("custom_eligibility_rules_json", sa.Text(), nullable=True, server_default="{}"),
    )
    _add("applications",
        sa.Column("drive_id", sa.String(), nullable=True),
        sa.Column("pipeline_stage_key", sa.String(length=120), nullable=True, server_default="registration"),
    )
    _add("communication_messages",
        sa.Column("attachment_path", sa.String(length=700), nullable=True),
        sa.Column("attachment_filename", sa.String(length=300), nullable=True),
        sa.Column("attachment_mime", sa.String(length=120), nullable=True),
        sa.Column("attachment_size", sa.Integer(), nullable=True),
    )
    _ensure_index("recruiter_profiles", "ix_recruiter_profiles_cin", ["cin"])
    _ensure_index("recruiter_profiles", "ix_recruiter_profiles_gstin", ["gstin"])
    _ensure_index("applications", "ix_applications_drive_id", ["drive_id"])
    _ensure_fk("applications", "fk_applications_drive_id", "placement_drives", ["drive_id"], ["id"])

    # All additional enterprise entities are new tables; SQLAlchemy metadata creates
    # only the tables that do not already exist, leaving migrated legacy tables intact.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for table in [
        "profile_change_requests", "custom_field_values", "custom_field_definitions",
        "incident_reports", "communication_messages", "communication_threads",
        "announcements", "attendance_records", "attendance_sessions", "student_documents",
        "offers", "institution_policies", "notification_preferences", "notifications",
        "interview_evaluations", "interview_schedules", "drive_stages",
    ]:
        op.drop_table(table)
    op.drop_constraint("fk_applications_drive_id", "applications", type_="foreignkey")
    op.drop_index("ix_applications_drive_id", table_name="applications")
    for col in ["pipeline_stage_key", "drive_id"]:
        op.drop_column("applications", col)
    for col in [
        "custom_eligibility_rules_json", "required_documents_json", "required_certifications_json",
        "required_skills_json", "allow_placed_students", "work_authorization_required",
        "max_academic_gap_months", "max_historical_backlogs", "max_active_backlogs",
        "min_diploma_percentage", "min_twelfth_percentage", "min_tenth_percentage",
    ]:
        op.drop_column("placement_drives", col)
    op.drop_index("ix_recruiter_profiles_gstin", table_name="recruiter_profiles")
    op.drop_index("ix_recruiter_profiles_cin", table_name="recruiter_profiles")
    for col in [
        "company_verification_confidence", "company_verification_status", "suspicious_domain",
        "job_consistency_score", "previous_successful_placements", "past_college_relationships_json",
        "authorization_letter_path", "official_email_domain", "company_address", "gstin", "cin",
    ]:
        op.drop_column("recruiter_profiles", col)
    for col in [
        "offers_count", "placement_status", "certifications_json", "work_authorization",
        "academic_gap_months", "historical_backlogs", "active_backlogs", "diploma_percentage",
        "twelfth_percentage", "tenth_percentage",
    ]:
        op.drop_column("student_profiles", col)
