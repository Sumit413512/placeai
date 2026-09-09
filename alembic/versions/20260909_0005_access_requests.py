"""PlaceAI production access requests.

Revision ID: 20260909_0005
Revises: 20260908_0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260909_0005"
down_revision = "20260908_0004"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {i.get("name") for i in inspector.get_indexes(table)} if table in inspector.get_table_names() else set()


def upgrade() -> None:
    if "access_requests" not in _tables():
        op.create_table(
            "access_requests",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("requested_role", sa.String(length=40), nullable=False),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("work_email", sa.String(length=320), nullable=False),
            sa.Column("organization_name", sa.String(length=250), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
            sa.Column("reviewed_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint(
                "requested_role IN ('recruiter','institution_admin','platform_admin')",
                name="ck_access_requests_role",
            ),
            sa.CheckConstraint(
                "status IN ('new','under_review','approved','rejected','provisioned')",
                name="ck_access_requests_status",
            ),
        )
    idx = _indexes("access_requests")
    if "ix_access_requests_requested_role" not in idx:
        op.create_index("ix_access_requests_requested_role", "access_requests", ["requested_role"])
    if "ix_access_requests_work_email" not in idx:
        op.create_index("ix_access_requests_work_email", "access_requests", ["work_email"])
    if "ix_access_requests_status" not in idx:
        op.create_index("ix_access_requests_status", "access_requests", ["status"])
    if "ix_access_requests_created_at" not in idx:
        op.create_index("ix_access_requests_created_at", "access_requests", ["created_at"])
    if "ix_access_requests_reviewed_by_user_id" not in idx:
        op.create_index("ix_access_requests_reviewed_by_user_id", "access_requests", ["reviewed_by_user_id"])


def downgrade() -> None:
    if "access_requests" in _tables():
        op.drop_table("access_requests")
