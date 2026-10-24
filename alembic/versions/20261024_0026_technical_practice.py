"""Private technical practice attempts; no changes to interview scores."""
from alembic import op
import sqlalchemy as sa

revision = '20261024_0026'
down_revision = '20261024_0025'
branch_labels = None
depends_on = None


def upgrade():
    from app.technical_practice import TechnicalPracticeAttempt
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql' and bind.execute(sa.text('SELECT current_user')).scalar() == 'placeai_render_runtime':
        if not sa.inspect(bind).has_table('technical_practice_attempts'):
            raise RuntimeError('Provision the private technical practice schema with its owner before deploying.')
        columns = {column['name'] for column in sa.inspect(bind).get_columns('technical_practice_attempts')}
        if not set(TechnicalPracticeAttempt.__table__.columns.keys()) <= columns:
            raise RuntimeError('The technical practice schema is incomplete.')
        if not bind.execute(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid='public.technical_practice_attempts'::regclass")).scalar():
            raise RuntimeError('Technical practice storage must have RLS enabled.')
        return
    TechnicalPracticeAttempt.__table__.create(bind, checkfirst=True)
    if bind.dialect.name == 'postgresql':
        op.execute('ALTER TABLE technical_practice_attempts ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON technical_practice_attempts FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            if bind.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}).scalar():
                op.execute(f'REVOKE ALL ON technical_practice_attempts FROM {role}')
        # No browser-facing role receives privileges or policies.
        if bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname='placeai_render_runtime'")).scalar():
            op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON technical_practice_attempts TO placeai_render_runtime')
            op.execute('DROP POLICY IF EXISTS technical_practice_runtime ON technical_practice_attempts')
            op.execute('CREATE POLICY technical_practice_runtime ON technical_practice_attempts FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)')


def downgrade():
    op.drop_table('technical_practice_attempts')
