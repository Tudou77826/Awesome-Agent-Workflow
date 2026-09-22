"""Archive requests can originate from the admin console without an event.

Revision ID: 0025_archive_request_source
Revises: 0024_telemetry_filter_config
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_archive_request_source"
down_revision = "0024_telemetry_filter_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    # event_id 放开为可空：业务页（工作流/归因）直接发起的申请没有异常事件。
    # source 标记发起入口：event=异常事件页，admin_console=业务运营页。
    with op.batch_alter_table("anomaly_archive_request", recreate="always") as batch:
        batch.alter_column("event_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(
            sa.Column("source", sa.String(32), nullable=False, server_default="event")
        )
        batch.create_check_constraint(
            "ck_anomaly_archive_source", "source IN ('event', 'admin_console')"
        )
    if dialect != "sqlite":
        # SQLite 的 server_default 在 batch 重建里已随表定义消失；其余库要显式去掉。
        op.alter_column("anomaly_archive_request", "source", server_default=None)


def downgrade() -> None:
    op.execute("DELETE FROM anomaly_archive_request WHERE event_id IS NULL")
    with op.batch_alter_table("anomaly_archive_request", recreate="always") as batch:
        batch.drop_constraint("ck_anomaly_archive_source", type_="check")
        batch.drop_column("source")
        batch.alter_column("event_id", existing_type=sa.Uuid(), nullable=False)
