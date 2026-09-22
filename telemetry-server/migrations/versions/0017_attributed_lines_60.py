"""Add the 60-percent attribution bucket used by the testing dashboard."""

import sqlalchemy as sa
from alembic import op

revision = "0017_attributed_lines_60"
down_revision = "0016_ai_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "code_attribution",
        sa.Column("attributed_lines_60", sa.Integer(), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，batch 重建把 CHECK 写进表定义。
        with op.batch_alter_table("code_attribution", recreate="always") as batch:
            batch.create_check_constraint(
                "ck_attribution_60_threshold_order",
                "attributed_lines_60 IS NULL OR attributed_lines_80 <= attributed_lines_60",
            )
            batch.create_check_constraint(
                "ck_attribution_60_not_over_total",
                "attributed_lines_60 IS NULL OR attributed_lines_60 <= dev_effective_lines",
            )
    else:
        op.create_check_constraint(
            "ck_attribution_60_threshold_order",
            "code_attribution",
            "attributed_lines_60 IS NULL OR attributed_lines_80 <= attributed_lines_60",
        )
        op.create_check_constraint(
            "ck_attribution_60_not_over_total",
            "code_attribution",
            "attributed_lines_60 IS NULL OR attributed_lines_60 <= dev_effective_lines",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("code_attribution", recreate="always") as batch:
            batch.drop_constraint("ck_attribution_60_not_over_total", type_="check")
            batch.drop_constraint("ck_attribution_60_threshold_order", type_="check")
    else:
        op.drop_constraint(
            "ck_attribution_60_not_over_total",
            "code_attribution",
            type_="check",
        )
        op.drop_constraint(
            "ck_attribution_60_threshold_order",
            "code_attribution",
            type_="check",
        )
    op.drop_column("code_attribution", "attributed_lines_60")
