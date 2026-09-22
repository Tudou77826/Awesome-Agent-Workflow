"""Add server-managed telemetry filter config history.

Revision ID: 0024_telemetry_filter_config
Revises: 0023_anomaly_rule_archive_control
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0024_telemetry_filter_config"
down_revision = "0023_anomaly_rule_archive_control"
branch_labels = None
depends_on = None

_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=3), "mysql")


def upgrade() -> None:
    op.create_table(
        "telemetry_filter_config",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", _DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )


def downgrade() -> None:
    op.drop_table("telemetry_filter_config")
