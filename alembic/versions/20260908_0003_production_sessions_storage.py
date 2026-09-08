"""PlaceAI 3.1.3 production session revocation and durable file storage.

Revision ID: 20260908_0003
Revises: 20260905_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260908_0003"
down_revision = "20260905_0002"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()


def _indexes(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {i.get("name") for i in inspector.get_indexes(table)} if table in inspector.get_table_names() else set()


def upgrade() -> None:
    if "auth_version" not in _columns("users"):
        op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"))

    if "refresh_sessions" not in _tables():
        op.create_table(
            "refresh_sessions",
            sa.Column("jti", sa.String(length=120), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("auth_version", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    idx = _indexes("refresh_sessions")
    if "ix_refresh_sessions_user_id" not in idx:
        op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    if "ix_refresh_sessions_expires_at" not in idx:
        op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])
    if "ix_refresh_sessions_revoked_at" not in idx:
        op.create_index("ix_refresh_sessions_revoked_at", "refresh_sessions", ["revoked_at"])

    if "stored_files" not in _tables():
        op.create_table(
            "stored_files",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("category", sa.String(length=120), nullable=False),
            sa.Column("original_filename", sa.String(length=300), nullable=False),
            sa.Column("mime_type", sa.String(length=160), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("data", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    idx = _indexes("stored_files")
    if "ix_stored_files_category" not in idx:
        op.create_index("ix_stored_files_category", "stored_files", ["category"])
    if "ix_stored_files_created_at" not in idx:
        op.create_index("ix_stored_files_created_at", "stored_files", ["created_at"])


def downgrade() -> None:
    tables = _tables()
    if "stored_files" in tables:
        op.drop_table("stored_files")
    if "refresh_sessions" in tables:
        op.drop_table("refresh_sessions")
    if "users" in tables and "auth_version" in _columns("users"):
        op.drop_column("users", "auth_version")
