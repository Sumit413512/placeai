"""Retire the legacy public sales-lead table.

Revision ID: 20260910_0006
Revises: 20260909_0005
"""
from alembic import op
from sqlalchemy import inspect

revision = "20260910_0006"
down_revision = "20260909_0005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "demo_requests" in inspect(op.get_bind()).get_table_names():
        op.drop_table("demo_requests")

def downgrade() -> None:
    # Intentionally irreversible: the retired table contained no production records.
    pass
