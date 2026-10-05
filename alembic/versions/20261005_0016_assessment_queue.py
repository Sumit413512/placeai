"""Private durable assessment grading queue.

Revision ID: 20261005_0016
Revises: 20261003_0015
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0016"
down_revision = "20261003_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assessment_jobs",
        sa.Column("interview_id", sa.String(), sa.ForeignKey("mock_interviews.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_assessment_jobs_available_at", "assessment_jobs", ["available_at"])
    op.create_index("ix_assessment_jobs_state_lease", "assessment_jobs", ["state", "lease_until"])
    op.create_table("assessment_queue_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("starts_in_window", sa.Integer(), nullable=False))
    op.execute(sa.text("INSERT INTO assessment_queue_control (id, window_started_at, starts_in_window) VALUES (1, CURRENT_TIMESTAMP, 0)"))
    if op.get_bind().dialect.name == "postgresql":
        for table in ("assessment_jobs", "assessment_queue_control"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")


def downgrade():
    op.drop_table("assessment_queue_control")
    op.drop_table("assessment_jobs")
