"""Private, durable learning notebooks and generation leases.

Restricted Render runtimes verify owner-provisioned DDL instead of escalating privileges.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261010_0020"
down_revision = "20261007_0019"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS public.learning_notebooks (
 id varchar PRIMARY KEY,
 user_id varchar NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
 request_id varchar(80) NOT NULL,
 title varchar(240) NOT NULL,
 state varchar(24) NOT NULL DEFAULT 'queued',
 input_json text NOT NULL,
 plan_json text NOT NULL DEFAULT '{}',
 chapters_json text NOT NULL DEFAULT '[]',
 sources_json text NOT NULL DEFAULT '[]',
 evidence text NOT NULL DEFAULT '',
 provider varchar(180),
 attempts integer NOT NULL DEFAULT 0,
 error_code varchar(80),
 available_at timestamp NOT NULL DEFAULT timezone('utc', now()),
 lease_until timestamp,
 lease_token varchar(40),
 created_at timestamp NOT NULL DEFAULT timezone('utc', now()),
 updated_at timestamp NOT NULL DEFAULT timezone('utc', now()),
 CONSTRAINT uq_learning_request UNIQUE(user_id, request_id)
);
CREATE INDEX IF NOT EXISTS ix_learning_owner_created ON public.learning_notebooks(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_learning_queue ON public.learning_notebooks(state, available_at);
ALTER TABLE public.learning_notebooks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.learning_notebooks FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_notebooks TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_learning_runtime ON public.learning_notebooks;
CREATE POLICY placeai_learning_runtime ON public.learning_notebooks
 FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
CREATE TABLE IF NOT EXISTS public.learning_runtime (
 id integer PRIMARY KEY,
 provider_configured boolean NOT NULL DEFAULT false,
 checked_at timestamp NOT NULL DEFAULT timezone('utc', now())
);
ALTER TABLE public.learning_runtime ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.learning_runtime FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_runtime TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_learning_runtime_status ON public.learning_runtime;
CREATE POLICY placeai_learning_runtime_status ON public.learning_runtime
 FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
"""


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        from app.models import LearningNotebook, LearningRuntime
        LearningNotebook.__table__.create(bind, checkfirst=True)
        LearningRuntime.__table__.create(bind, checkfirst=True)
        return
    if bind.execute(sa.text("SELECT current_user")).scalar() != "placeai_render_runtime":
        for statement in DDL.split(";"):
            if statement.strip():
                bind.execute(sa.text(statement))
    valid = bind.execute(sa.text("""
      SELECT bool_and(access_ok) AND count(*)=2 FROM (
      SELECT c.relrowsecurity
        AND has_table_privilege('placeai_render_runtime', c.oid, 'SELECT')
        AND has_table_privilege('placeai_render_runtime', c.oid, 'INSERT')
        AND has_table_privilege('placeai_render_runtime', c.oid, 'UPDATE')
        AND has_table_privilege('placeai_render_runtime', c.oid, 'DELETE')
        AND NOT has_table_privilege('anon', c.oid, 'SELECT')
        AND NOT has_table_privilege('authenticated', c.oid, 'SELECT')
        AND EXISTS(SELECT 1 FROM pg_policies p WHERE p.schemaname='public'
                   AND p.tablename=c.relname
                   AND p.policyname=CASE WHEN c.relname='learning_notebooks'
                       THEN 'placeai_learning_runtime' ELSE 'placeai_learning_runtime_status' END
                   AND p.qual='true' AND p.with_check='true'
                   AND CAST('placeai_render_runtime' AS name)=ANY(p.roles)) AS access_ok
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN ('learning_notebooks','learning_runtime')
      ) AS access_checks
    """)).scalar()
    if not valid:
        raise RuntimeError("LEARNING_PRIVATE_RUNTIME_ACCESS_NOT_PROVISIONED")


def downgrade():
    # Removing a feature must not destroy students' saved educational content.
    pass
