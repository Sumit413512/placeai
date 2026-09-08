"""PlaceAI 3.1.3 durable abuse-rate limiting.

Revision ID: 20260908_0004
Revises: 20260908_0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260908_0004"
down_revision = "20260908_0003"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {i.get("name") for i in inspector.get_indexes(table)} if table in inspector.get_table_names() else set()


def upgrade() -> None:
    if "rate_limit_buckets" not in _tables():
        op.create_table(
            "rate_limit_buckets",
            sa.Column("key_hash", sa.String(length=64), primary_key=True),
            sa.Column("scope", sa.String(length=80), nullable=False),
            sa.Column("window_started_at", sa.DateTime(), nullable=False),
            sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("blocked_until", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    idx = _indexes("rate_limit_buckets")
    if "ix_rate_limit_buckets_scope" not in idx:
        op.create_index("ix_rate_limit_buckets_scope", "rate_limit_buckets", ["scope"])
    if "ix_rate_limit_buckets_blocked_until" not in idx:
        op.create_index("ix_rate_limit_buckets_blocked_until", "rate_limit_buckets", ["blocked_until"])


def downgrade() -> None:
    if "rate_limit_buckets" in _tables():
        op.drop_table("rate_limit_buckets")
