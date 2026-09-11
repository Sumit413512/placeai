"""Add PII-free transactional email delivery observability.

Revision ID: 20260911_0008
Revises: 20260911_0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260911_0008"
down_revision = "20260911_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "email_delivery_events" in inspect(bind).get_table_names():
        return
    op.create_table(
        "email_delivery_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_delivery_events_purpose", "email_delivery_events", ["purpose"], unique=False)
    op.create_index("ix_email_delivery_events_outcome", "email_delivery_events", ["outcome"], unique=False)
    op.create_index("ix_email_delivery_events_created_at", "email_delivery_events", ["created_at"], unique=False)
    op.create_index("ix_email_delivery_events_purpose_created_at", "email_delivery_events", ["purpose", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if "email_delivery_events" in inspect(bind).get_table_names():
        op.drop_table("email_delivery_events")
