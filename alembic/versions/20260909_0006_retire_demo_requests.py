"""Retire obsolete demo request storage.

Revision ID: 20260909_0006
Revises: 20260909_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260909_0006"
down_revision = "20260909_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "demo_requests" in inspect(op.get_bind()).get_table_names():
        op.drop_table("demo_requests")


def downgrade() -> None:
    if "demo_requests" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "demo_requests",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("contact_name", sa.String(length=200), nullable=False),
            sa.Column("work_email", sa.String(length=320), nullable=False),
            sa.Column("organization_name", sa.String(length=250), nullable=False),
            sa.Column("role_title", sa.String(length=180), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("student_count", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
