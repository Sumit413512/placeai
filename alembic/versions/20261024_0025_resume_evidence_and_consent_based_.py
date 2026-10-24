"""resume evidence and consent based academic vault

Revision ID: 20261024_0025
Revises: 43e6ac3c4be8
Create Date: 2026-10-24 02:22:58.469069
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20261024_0025'
down_revision: Union[str, None] = '43e6ac3c4be8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        'student_profiles': [('target_role', sa.String(160)), ('role_requirements_json', sa.Text()),
                             ('current_semester', sa.Integer()), ('enrollment_number', sa.String(80)), ('academic_year', sa.String(40))],
        'resumes': [('evidence_review_json', sa.Text())],
        'student_documents': [('semester', sa.Integer()), ('label', sa.String(160)),
                              ('shared_organization_id', sa.String()), ('shared_at', sa.DateTime())],
    }
    runtime = bind.dialect.name == 'postgresql' and bind.execute(sa.text('SELECT current_user')).scalar() == 'placeai_render_runtime'
    for table, fields in columns.items():
        present = {x['name'] for x in sa.inspect(bind).get_columns(table)}
        for name, kind in fields:
            if name not in present:
                if runtime:
                    raise RuntimeError('Provision evidence/vault columns before this release; preserve existing records')
                op.add_column(table, sa.Column(name, kind, nullable=True))
    if bind.dialect.name == 'postgresql':
        constraints = {x['name'] for x in sa.inspect(bind).get_foreign_keys('student_documents')}
        if 'fk_document_shared_org' not in constraints:
            if runtime:
                raise RuntimeError('Provision the document institution reference before deployment')
            op.create_foreign_key('fk_document_shared_org', 'student_documents', 'organizations', ['shared_organization_id'], ['id'])
    # Existing uploads stay stored; no historical visibility choice is treated as new consent.

def downgrade() -> None:
    raise RuntimeError('Forward-only: retain review evidence and document submission records')
