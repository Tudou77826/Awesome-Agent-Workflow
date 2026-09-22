"""Add reporter to portal issues.

Revision ID: 0009_issue_reporter
Revises: 0008_issue_tracker
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_issue_reporter"
down_revision = "0008_issue_tracker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing deployments may already have issues, so add a temporary default before
    # enforcing the non-null application invariant.
    op.add_column(
        "issue",
        sa.Column("reporter", sa.String(100), nullable=False, server_default="未知提出人"),
    )
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 不支持 ALTER COLUMN DROP DEFAULT，用 batch 重建去掉 server_default。
        with op.batch_alter_table("issue", recreate="always") as batch:
            batch.alter_column("reporter", existing_type=sa.String(100), server_default=None)
    else:
        op.alter_column("issue", "reporter", server_default=None)


def downgrade() -> None:
    op.drop_column("issue", "reporter")
