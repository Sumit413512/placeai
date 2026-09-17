"""Harden access-request resolver search path.

Revision ID: 20260918_0010
Revises: 20260917_0009
"""
from alembic import op

revision = "20260918_0010"
down_revision = "20260917_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER FUNCTION public.placeai_resolve_access_request_organization() "
        "SET search_path = public, pg_temp"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER FUNCTION public.placeai_resolve_access_request_organization() "
        "RESET search_path"
    )
