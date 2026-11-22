"""Add the Arrays readiness workflow."""

from alembic import op
import sqlalchemy as sa

revision = "20261122_0030"
down_revision = "20261110_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "array_readiness",
        sa.Column("student_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("scope", sa.String(100), primary_key=True),
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("diagnostic_answer", sa.SmallInteger()),
        sa.Column("practice_answer", sa.SmallInteger()),
        sa.Column("followup_answer", sa.SmallInteger()),
    )
    op.create_index("ix_array_readiness_institution", "array_readiness", ["organization_id", "student_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.array_readiness ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON public.array_readiness FROM PUBLIC, anon, authenticated")
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.array_readiness TO service_role, placeai_render_runtime")
        op.execute(
            "CREATE POLICY placeai_backend_runtime ON public.array_readiness "
            "FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)"
        )


def downgrade():
    op.drop_table("array_readiness")
