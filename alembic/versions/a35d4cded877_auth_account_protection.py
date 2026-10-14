"""auth_account_protection

Revision ID: a35d4cded877
Revises: 20261010_0020
Create Date: 2026-10-14 15:15:58.150517
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a35d4cded877'
down_revision: Union[str, None] = '20261010_0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DDL = """
CREATE TABLE IF NOT EXISTS public.account_protection (
 user_id varchar PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
 verification_required boolean NOT NULL DEFAULT false,
 email_token_hash varchar(64) UNIQUE,
 email_token_expires timestamp,
 mfa_secret text,
 mfa_pending text,
 mfa_pending_expires timestamp,
 mfa_last_counter integer NOT NULL DEFAULT -1,
 recovery_hashes text NOT NULL DEFAULT '[]',
 challenge_hash varchar(64) UNIQUE,
 challenge_expires timestamp,
 challenge_version integer
);
ALTER TABLE public.account_protection ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.account_protection FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.account_protection TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_account_protection_runtime ON public.account_protection;
CREATE POLICY placeai_account_protection_runtime ON public.account_protection
 FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
"""

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        from app.models import AccountProtection
        AccountProtection.__table__.create(bind, checkfirst=True)
        return
    if bind.execute(sa.text("SELECT current_user")).scalar() != "placeai_render_runtime":
        for statement in DDL.split(";"):
            if statement.strip():
                bind.execute(sa.text(statement))
    valid = bind.execute(sa.text("""
      SELECT c.relrowsecurity
        AND has_table_privilege('placeai_render_runtime',c.oid,'SELECT')
        AND has_table_privilege('placeai_render_runtime',c.oid,'INSERT')
        AND has_table_privilege('placeai_render_runtime',c.oid,'UPDATE')
        AND has_table_privilege('placeai_render_runtime',c.oid,'DELETE')
        AND NOT has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE')
        AND NOT has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE')
        AND EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname='public'
          AND p.tablename='account_protection' AND p.policyname='placeai_account_protection_runtime'
          AND p.qual='true' AND p.with_check='true' AND 'placeai_render_runtime'::name=ANY(p.roles))
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname='account_protection'
    """)).scalar()
    if not valid:
        raise RuntimeError("ACCOUNT_PROTECTION_PRIVATE_ACCESS_NOT_PROVISIONED")

def downgrade() -> None:
    # Preserve credentials and recovery state if application code is rolled back.
    pass
