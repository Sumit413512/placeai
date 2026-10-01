"""Add paid Career Roadmap generation and feature entitlements.

Revision ID: 20261001_0014
Revises: 20260925_0013
"""
from alembic import op
import sqlalchemy as sa

revision = "20261001_0014"
down_revision = "20260925_0013"
branch_labels = None
depends_on = None


def _create_student_feature_purchases() -> None:
    op.create_table(
        "student_feature_purchases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("feature_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_order_id", sa.String(length=180), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=180), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("provider_payment_id"),
    )
    op.create_index("ix_student_feature_purchases_student_id", "student_feature_purchases", ["student_id"])
    op.create_index("ix_student_feature_purchases_feature_code", "student_feature_purchases", ["feature_code"])
    op.create_index("ix_student_feature_purchases_status", "student_feature_purchases", ["status"])
    op.create_index(
        "ix_student_feature_purchases_student_feature_status",
        "student_feature_purchases",
        ["student_id", "feature_code", "status"],
    )


def _create_career_roadmaps() -> None:
    op.create_table(
        "career_roadmaps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("student_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("target_role", sa.String(length=200), nullable=True),
        sa.Column("target_field", sa.String(length=200), nullable=True),
        sa.Column("market_region", sa.String(length=120), nullable=False, server_default="India"),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("market_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("roadmap_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ai_provider", sa.String(length=40), nullable=True),
        sa.Column("ai_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_career_roadmaps_student_id", "career_roadmaps", ["student_id"])
    op.create_index("ix_career_roadmaps_student_created", "career_roadmaps", ["student_id", "created_at"])


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Production Supabase is intentionally migrated before application rollout so
    # Vercel never serves code that references missing tables. Render subsequently
    # runs Alembic on startup; these existence checks make that ordered rollout safe.
    if not inspector.has_table("student_feature_purchases"):
        _create_student_feature_purchases()
    if not inspector.has_table("career_roadmaps"):
        _create_career_roadmaps()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE public.student_feature_purchases ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.career_roadmaps ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON TABLE public.student_feature_purchases FROM anon, authenticated")
        op.execute("REVOKE ALL ON TABLE public.career_roadmaps FROM anon, authenticated")

        # The web/API clients never query these tables through PostgREST. The
        # restricted Render runtime connects directly to Postgres, so it needs
        # explicit DML grants plus an RLS policy. This preserves backend-only
        # access without granting anon/authenticated any table privileges.
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "public.student_feature_purchases TO placeai_render_runtime"
        )
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "public.career_roadmaps TO placeai_render_runtime"
        )
        for table_name in ("student_feature_purchases", "career_roadmaps"):
            op.execute(f"DROP POLICY IF EXISTS placeai_backend_access ON public.{table_name}")
            op.execute(
                f"CREATE POLICY placeai_backend_access ON public.{table_name} "
                "FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("career_roadmaps"):
        op.drop_index("ix_career_roadmaps_student_created", table_name="career_roadmaps")
        op.drop_index("ix_career_roadmaps_student_id", table_name="career_roadmaps")
        op.drop_table("career_roadmaps")
    if inspector.has_table("student_feature_purchases"):
        op.drop_index("ix_student_feature_purchases_student_feature_status", table_name="student_feature_purchases")
        op.drop_index("ix_student_feature_purchases_status", table_name="student_feature_purchases")
        op.drop_index("ix_student_feature_purchases_feature_code", table_name="student_feature_purchases")
        op.drop_index("ix_student_feature_purchases_student_id", table_name="student_feature_purchases")
        op.drop_table("student_feature_purchases")
