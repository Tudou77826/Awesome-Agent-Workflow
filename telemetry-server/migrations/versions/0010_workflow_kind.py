"""Add an internal workflow category for dashboard and ingestion isolation.

Revision ID: 0010_workflow_kind
Revises: 0009_issue_reporter, 0008_task_execution_identity
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_workflow_kind"
down_revision = ("0009_issue_reporter", "0008_task_execution_identity")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows predate categories and therefore belong to the original AAW flow.
    op.add_column(
        "workflow_run",
        sa.Column("workflow_kind", sa.String(32), nullable=False, server_default="aaw"),
    )
    op.add_column(
        "telemetry_message",
        sa.Column("workflow_kind", sa.String(32), nullable=False, server_default="aaw"),
    )
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 不支持 ALTER COLUMN DROP DEFAULT，用 batch 重建去掉 server_default。
        with op.batch_alter_table("workflow_run", recreate="always") as batch:
            batch.alter_column("workflow_kind", existing_type=sa.String(32), server_default=None)
        with op.batch_alter_table("telemetry_message", recreate="always") as batch:
            batch.alter_column("workflow_kind", existing_type=sa.String(32), server_default=None)
    else:
        op.alter_column("workflow_run", "workflow_kind", server_default=None)
        op.alter_column("telemetry_message", "workflow_kind", server_default=None)
    op.create_index(
        "ix_workflow_kind_project_started",
        "workflow_run",
        ["workflow_kind", "project_key", "started_at"],
    )
    op.create_index(
        "ix_message_kind_user_updated",
        "telemetry_message",
        ["workflow_kind", "user_email", "client_updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_kind_user_updated", table_name="telemetry_message")
    op.drop_index("ix_workflow_kind_project_started", table_name="workflow_run")
    op.drop_column("telemetry_message", "workflow_kind")
    op.drop_column("workflow_run", "workflow_kind")
