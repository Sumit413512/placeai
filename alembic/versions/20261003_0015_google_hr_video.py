"""Private Google bindings and HR exam recordings.

Revision ID: 20261003_0015
Revises: 20261001_0014
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0015"
down_revision = "20261001_0014"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("google_identities"):
        op.create_table("google_identities",
            sa.Column("subject", sa.String(255), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(), nullable=False))
    if not inspector.has_table("hr_recordings"):
        op.create_table("hr_recordings",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("interview_id", sa.String(), sa.ForeignKey("mock_interviews.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="ready"),
            sa.Column("mime_type", sa.String(80)),
            sa.Column("exam_started_at", sa.DateTime()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("deadline_at", sa.DateTime()),
            sa.Column("consent_at", sa.DateTime()),
            sa.Column("sealed_at", sa.DateTime()),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("segments_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("analysis_json", sa.Text()),
            sa.Column("analysis_lease_until", sa.DateTime()),
            sa.Column("evaluation_lease_until", sa.DateTime()),
            sa.Column("submission_json", sa.Text()),
            sa.Column("provider_file_name", sa.String(200)),
            sa.Column("created_at", sa.DateTime(), nullable=False))
        op.create_index("ix_hr_recordings_expires_at", "hr_recordings", ["expires_at"])
    if not inspector.has_table("hr_video_chunks"):
        op.create_table("hr_video_chunks",
            sa.Column("recording_id", sa.String(), sa.ForeignKey("hr_recordings.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("sequence", sa.Integer(), primary_key=True),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False))
    if bind.dialect.name == "postgresql":
        for table in ("google_identities", "hr_recordings", "hr_video_chunks"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated")


def downgrade():
    for table in ("hr_video_chunks", "hr_recordings", "google_identities"):
        op.drop_table(table)
