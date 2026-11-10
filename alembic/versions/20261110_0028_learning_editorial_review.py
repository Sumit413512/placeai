"""Add human editorial review gates for generated learning content."""
from alembic import op
import sqlalchemy as sa

revision = "20261110_0028"
down_revision = "20261024_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_notebooks", sa.Column("shared_key", sa.String(64), nullable=True))
    op.create_index("ix_learning_notebooks_shared_key", "learning_notebooks", ["shared_key"])
    for table in ("learning_notebooks", "learning_video_courses", "learning_video_lessons"):
        op.add_column(table, sa.Column("editorial_status", sa.String(24), nullable=False,
                                       server_default="approved"))
        op.add_column(table, sa.Column("editorial_notes", sa.Text(), nullable=False,
                                       server_default=""))
        op.add_column(table, sa.Column("reviewed_by_user_id", sa.String(), nullable=True))
        op.add_column(table, sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        op.create_index(f"ix_{table}_editorial_status", table, ["editorial_status"])
        op.create_foreign_key(f"fk_{table}_reviewed_by", table, "users",
                              ["reviewed_by_user_id"], ["id"], ondelete="SET NULL")
        op.alter_column(table, "editorial_status", server_default="generating")


def downgrade():
    for table in reversed(("learning_notebooks", "learning_video_courses", "learning_video_lessons")):
        op.drop_constraint(f"fk_{table}_reviewed_by", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_editorial_status", table_name=table)
        for column in ("reviewed_at", "reviewed_by_user_id", "editorial_notes", "editorial_status"):
            op.drop_column(table, column)
    op.drop_index("ix_learning_notebooks_shared_key", table_name="learning_notebooks")
    op.drop_column("learning_notebooks", "shared_key")
