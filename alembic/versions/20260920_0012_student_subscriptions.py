"""Add independent student subscription entitlements.

Revision ID: 20260920_0012
Revises: 20260920_0011
"""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0012"
down_revision = "20260920_0011"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "student_subscriptions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("plan_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=160), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=160), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_subscription_id"),
    )
    op.create_index("ix_student_subscriptions_student_id","student_subscriptions",["student_id"])
    op.create_index("ix_student_subscriptions_student_status","student_subscriptions",["student_id","status"])
    op.create_index("ix_student_subscriptions_expires_at","student_subscriptions",["expires_at"])

def downgrade() -> None:
    op.drop_index("ix_student_subscriptions_expires_at",table_name="student_subscriptions")
    op.drop_index("ix_student_subscriptions_student_status",table_name="student_subscriptions")
    op.drop_index("ix_student_subscriptions_student_id",table_name="student_subscriptions")
    op.drop_table("student_subscriptions")
