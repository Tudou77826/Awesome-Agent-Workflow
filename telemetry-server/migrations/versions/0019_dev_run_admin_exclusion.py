"""Add admin exclusion (无关化) governance fields to dev_run.

Revision ID: 0019_dev_run_admin_exclusion
Revises: 0018_registry_tables
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0019_dev_run_admin_exclusion"
down_revision = "0018_registry_tables"
branch_labels = None
depends_on = None

_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=3), "mysql")


def upgrade() -> None:
    op.add_column(
        "dev_run",
        sa.Column(
            "admin_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "dev_run", sa.Column("admin_excluded_reason", sa.String(512), nullable=True)
    )
    op.add_column("dev_run", sa.Column("admin_excluded_at", _DATETIME, nullable=True))
    op.add_column(
        "dev_run", sa.Column("admin_excluded_by", sa.String(128), nullable=True)
    )
    op.create_index(
        "ix_dev_admin_excluded", "dev_run", ["admin_excluded"]
    )


def downgrade() -> None:
    op.drop_index("ix_dev_admin_excluded", table_name="dev_run")
    op.drop_column("dev_run", "admin_excluded_by")
    op.drop_column("dev_run", "admin_excluded_at")
    op.drop_column("dev_run", "admin_excluded_reason")
    op.drop_column("dev_run", "admin_excluded")
