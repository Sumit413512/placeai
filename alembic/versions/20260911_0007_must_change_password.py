"""Require newly provisioned accounts to rotate temporary passwords.

Revision ID: 20260911_0007
Revises: 20260910_0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260911_0007"
down_revision = "20260910_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "must_change_password" not in columns:
        op.add_column(
            "users",
            sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "must_change_password" in columns:
        op.drop_column("users", "must_change_password")
