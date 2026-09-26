"""Add persisted placement action control loop.

Revision ID: 20260925_0013
Revises: 20260920_0012
"""
from alembic import op
import sqlalchemy as sa

revision = "20260925_0013"
down_revision = "20260920_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "placement_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=True),
        sa.Column("drive_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("owner_user_id", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=240), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_outcome", sa.String(length=80), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["drive_id"], ["placement_drives.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "source_key", name="uq_placement_action_org_source"),
    )
    op.create_index("ix_placement_actions_org_status", "placement_actions", ["organization_id", "status"])
    op.create_index("ix_placement_actions_student_status", "placement_actions", ["student_id", "status"])
    op.create_index("ix_placement_actions_drive", "placement_actions", ["drive_id"])
    op.create_index("ix_placement_actions_due_at", "placement_actions", ["due_at"])
    op.create_index("ix_placement_actions_priority", "placement_actions", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_placement_actions_priority", table_name="placement_actions")
    op.drop_index("ix_placement_actions_due_at", table_name="placement_actions")
    op.drop_index("ix_placement_actions_drive", table_name="placement_actions")
    op.drop_index("ix_placement_actions_student_status", table_name="placement_actions")
    op.drop_index("ix_placement_actions_org_status", table_name="placement_actions")
    op.drop_table("placement_actions")
