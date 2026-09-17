"""Scope controlled access requests to institutions.

Revision ID: 20260917_0009
Revises: 20260911_0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260917_0009"
down_revision = "20260911_0008"
branch_labels = None
depends_on = None


def _columns(bind) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns("access_requests")}


def _indexes(bind) -> set[str]:
    return {index["name"] for index in inspect(bind).get_indexes("access_requests") if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    if "access_requests" not in inspect(bind).get_table_names():
        return

    if "organization_id" not in _columns(bind):
        with op.batch_alter_table("access_requests") as batch:
            batch.add_column(sa.Column("organization_id", sa.String(), nullable=True))
            batch.create_foreign_key(
                "fk_access_requests_organization_id_organizations",
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if "ix_access_requests_organization_id" not in _indexes(bind):
        op.create_index(
            "ix_access_requests_organization_id",
            "access_requests",
            ["organization_id"],
            unique=False,
        )

    # Backfill only exact active institution-name/slug matches. Unmatched legacy
    # requests remain platform-scoped instead of being guessed into a tenant.
    op.execute(
        sa.text(
            """
            UPDATE access_requests
            SET organization_id = (
                SELECT organizations.id
                FROM organizations
                WHERE organizations.is_active = true
                  AND (
                    lower(trim(organizations.name)) = lower(trim(access_requests.organization_name))
                    OR lower(trim(organizations.slug)) = lower(trim(access_requests.organization_name))
                  )
                ORDER BY CASE
                    WHEN lower(trim(organizations.name)) = lower(trim(access_requests.organization_name)) THEN 0
                    ELSE 1
                END, organizations.id
                LIMIT 1
            )
            WHERE organization_id IS NULL
              AND organization_name IS NOT NULL
              AND trim(organization_name) <> ''
            """
        )
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.placeai_resolve_access_request_organization()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              IF NEW.organization_id IS NULL
                 AND NEW.organization_name IS NOT NULL
                 AND btrim(NEW.organization_name) <> '' THEN
                SELECT o.id INTO NEW.organization_id
                FROM public.organizations o
                WHERE o.is_active IS TRUE
                  AND (
                    lower(btrim(o.name)) = lower(btrim(NEW.organization_name))
                    OR lower(btrim(o.slug)) = lower(btrim(NEW.organization_name))
                  )
                ORDER BY CASE
                    WHEN lower(btrim(o.name)) = lower(btrim(NEW.organization_name)) THEN 0
                    ELSE 1
                  END,
                  o.id
                LIMIT 1;
              END IF;
              RETURN NEW;
            END;
            $$;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_access_requests_resolve_organization ON public.access_requests")
        op.execute(
            """
            CREATE TRIGGER trg_access_requests_resolve_organization
            BEFORE INSERT OR UPDATE OF organization_name, organization_id
            ON public.access_requests
            FOR EACH ROW
            EXECUTE FUNCTION public.placeai_resolve_access_request_organization()
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "access_requests" not in inspect(bind).get_table_names():
        return

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_access_requests_resolve_organization ON public.access_requests")
        op.execute("DROP FUNCTION IF EXISTS public.placeai_resolve_access_request_organization()")

    if "ix_access_requests_organization_id" in _indexes(bind):
        op.drop_index("ix_access_requests_organization_id", table_name="access_requests")

    if "organization_id" in _columns(bind):
        with op.batch_alter_table("access_requests") as batch:
            batch.drop_column("organization_id")
