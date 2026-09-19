"""Add university/individual student entitlement and billing records.

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
    op.alter_column("incident_reports", "organization_id", existing_type=sa.String(), nullable=True)
    op.create_table(
        "individual_student_access",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="trialing"),
        sa.Column("trial_started_at", sa.DateTime(), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(), nullable=False),
        sa.Column("paid_access_until", sa.DateTime(), nullable=True),
        sa.Column("plan_code", sa.String(length=80), nullable=False, server_default="individual_pro_monthly"),
        sa.Column("payment_provider", sa.String(length=40), nullable=True),
        sa.Column("provider_customer_id", sa.String(length=160), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_individual_student_access_user_id", "individual_student_access", ["user_id"])
    op.create_index("ix_individual_student_access_status", "individual_student_access", ["status"])
    op.create_index("ix_individual_student_access_paid_access_until", "individual_student_access", ["paid_access_until"])

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("individual_access_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_order_id", sa.String(length=160), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=160), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["individual_access_id"], ["individual_student_access.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("provider_payment_id"),
    )
    op.create_index("ix_payment_transactions_user_id", "payment_transactions", ["user_id"])
    op.create_index("ix_payment_transactions_individual_access_id", "payment_transactions", ["individual_access_id"])
    op.create_index("ix_payment_transactions_provider_order_id", "payment_transactions", ["provider_order_id"])
    op.create_index("ix_payment_transactions_provider_payment_id", "payment_transactions", ["provider_payment_id"])
    op.create_index("ix_payment_transactions_status", "payment_transactions", ["status"])

    # Existing independent student accounts receive a fresh 3-day rollout trial rather
    # than being treated as expired because their account predates this entitlement model.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO individual_student_access (
                id, user_id, status, trial_started_at, trial_ends_at, plan_code, created_at, updated_at
            )
            SELECT
                gen_random_uuid()::text,
                u.id,
                'trialing',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP + INTERVAL '3 days',
                'individual_pro_monthly',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM users u
            LEFT JOIN student_profiles s ON s.user_id = u.id
            WHERE u.role::text = 'student'
              AND COALESCE(s.organization_id, u.organization_id) IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM individual_student_access a WHERE a.user_id = u.id
              )
            """
        )

        # Billing/entitlement records are backend-only. Unlike legacy tables, these
        # new sensitive tables are not exposed through Supabase anon/authenticated APIs.
        op.execute("ALTER TABLE public.individual_student_access ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.payment_transactions ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.alter_column("incident_reports", "organization_id", existing_type=sa.String(), nullable=False)
    op.drop_index("ix_payment_transactions_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_provider_payment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_provider_order_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_individual_access_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_user_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")
    op.drop_index("ix_individual_student_access_paid_access_until", table_name="individual_student_access")
    op.drop_index("ix_individual_student_access_status", table_name="individual_student_access")
    op.drop_index("ix_individual_student_access_user_id", table_name="individual_student_access")
    op.drop_table("individual_student_access")
