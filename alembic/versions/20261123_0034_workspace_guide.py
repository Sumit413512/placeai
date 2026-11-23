"""Offer the workspace guide to newly created accounts."""

import sqlalchemy as sa
from alembic import op

revision = "20261123_0034"
down_revision = "20261123_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("workspace_guide_pending", sa.Boolean(),
                                     nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "workspace_guide_pending")
