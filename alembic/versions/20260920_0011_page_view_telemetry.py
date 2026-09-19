"""Add privacy-safe page view telemetry for Platform Admin engagement.

Revision ID: 20260920_0011
Revises: 20260918_0010
"""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0011"
down_revision = "20260918_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_view_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("path", sa.String(length=240), nullable=False),
        sa.Column("referrer_host", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_view_events_created_at", "page_view_events", ["created_at"])
    op.create_index("ix_page_view_events_path", "page_view_events", ["path"])
    op.create_index("ix_page_view_events_session_hash", "page_view_events", ["session_hash"])
    op.create_index("ix_page_view_events_user_id", "page_view_events", ["user_id"])
    op.create_index("ix_page_view_events_visitor_hash", "page_view_events", ["visitor_hash"])
    op.create_index("ix_page_view_events_created_path", "page_view_events", ["created_at", "path"])
    op.create_index("ix_page_view_events_user_created", "page_view_events", ["user_id", "created_at"])
    op.create_index("ix_page_view_events_visitor_created", "page_view_events", ["visitor_hash", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_page_view_events_visitor_created", table_name="page_view_events")
    op.drop_index("ix_page_view_events_user_created", table_name="page_view_events")
    op.drop_index("ix_page_view_events_created_path", table_name="page_view_events")
    op.drop_index("ix_page_view_events_visitor_hash", table_name="page_view_events")
    op.drop_index("ix_page_view_events_user_id", table_name="page_view_events")
    op.drop_index("ix_page_view_events_session_hash", table_name="page_view_events")
    op.drop_index("ix_page_view_events_path", table_name="page_view_events")
    op.drop_index("ix_page_view_events_created_at", table_name="page_view_events")
    op.drop_table("page_view_events")
