"""One rule per detector and scope, so concurrent startup cannot duplicate rules.

Revision ID: 0026_anomaly_rule_unique_scope
Revises: 0025_archive_request_source

`--workers N` 启动时 N 个进程同时跑 ensure_builtin_rules，check-then-insert 会各自
插入一条：生产实测 14 个检测类型变成 28 条规则。这里补唯一性约束，并把存量重复行
收敛掉（保留最早一条，其余按"规则删除"收尾事件、留审计）。

`scope_value` 是平台级规则的 NULL 值——MySQL / SQLite 的唯一索引都视 NULL 为互不
相同，直接对 scope_value 建唯一索引对平台级规则完全不起作用，所以两端都要把 NULL
归一到空串：

* MySQL 不能对表达式建索引，改用两个虚拟生成列（scope_value_key 归一 NULL、
  is_active 在删除行上取 NULL）；
* SQLite / PostgreSQL 用表达式 + 部分唯一索引，status='deleted' 的行不参与。

已删除的规则不参与唯一性，因此删除后还能重新建同名规则。

含数据回填，必须在联机模式执行（部署走 `alembic upgrade head`），不能用于
`alembic upgrade --sql` 导出脚本。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "0026_anomaly_rule_unique_scope"
down_revision = "0025_archive_request_source"
branch_labels = None
depends_on = None

_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=3), "mysql")
_INDEX = "uq_anomaly_rule_detector_scope"
_ACTOR = "系统初始化"
_REASON = "多 worker 并发启动重复创建，保留最早一条"
_ENABLED_REASON = "收敛重复规则时保留原启用状态"


def _tables() -> dict[str, sa.Table]:
    return {
        "rule": sa.table(
            "anomaly_rule",
            sa.column("id", sa.Uuid()),
            sa.column("name", sa.String(128)),
            sa.column("category", sa.String(32)),
            sa.column("detector_type", sa.String(64)),
            sa.column("scope_type", sa.String(32)),
            sa.column("scope_value", sa.String(256)),
            sa.column("params", sa.JSON()),
            sa.column("allow_archive", sa.Boolean()),
            sa.column("status", sa.String(16)),
            sa.column("version", sa.Integer()),
            sa.column("change_reason", sa.String(512)),
            sa.column("updated_by", sa.String(128)),
            sa.column("created_at", _DATETIME),
            sa.column("updated_at", _DATETIME),
        ),
        "audit": sa.table(
            "anomaly_rule_audit",
            sa.column("id", sa.Uuid()),
            sa.column("rule_id", sa.Uuid()),
            sa.column("action", sa.String(32)),
            sa.column("version", sa.Integer()),
            sa.column("before", sa.JSON()),
            sa.column("after", sa.JSON()),
            sa.column("reason", sa.String(512)),
            sa.column("operator", sa.String(128)),
            sa.column("created_at", _DATETIME),
        ),
        "event": sa.table(
            "anomaly_event",
            sa.column("id", sa.Uuid()),
            sa.column("rule_id", sa.Uuid()),
            sa.column("detection_status", sa.String(16)),
            sa.column("closed_reason", sa.String(64)),
            sa.column("active_key", sa.String(64)),
            sa.column("disposition", sa.String(32)),
            sa.column("recovered_at", _DATETIME),
            sa.column("updated_at", _DATETIME),
        ),
        "request": sa.table(
            "anomaly_archive_request",
            sa.column("event_id", sa.Uuid()),
            sa.column("status", sa.String(16)),
            sa.column("review_note", sa.String(1000)),
            sa.column("reviewed_at", _DATETIME),
        ),
        "action": sa.table(
            "anomaly_action",
            sa.column("id", sa.Uuid()),
            sa.column("event_id", sa.Uuid()),
            sa.column("action", sa.String(64)),
            sa.column("actor", sa.String(128)),
            sa.column("details", sa.JSON()),
            sa.column("created_at", _DATETIME),
        ),
    }


def _snapshot(row: dict[str, Any], *, status: str, version: int) -> dict[str, Any]:
    return {
        "name": row["name"],
        "category": row["category"],
        "detector_type": row["detector_type"],
        "scope_type": row["scope_type"],
        "scope_value": row["scope_value"],
        "params": row["params"],
        "allow_archive": row["allow_archive"],
        "status": status,
        "version": version,
    }


def _close_rule_events(
    bind: sa.Connection, tables: dict[str, sa.Table], rule_id: Any, now: datetime
) -> list[dict[str, Any]]:
    """按"规则删除"语义收尾该规则名下仍活跃的事件，返回待写入的时间线动作。"""
    event = tables["event"]
    request = tables["request"]
    rows = (
        bind.execute(
            sa.select(event.c.id).where(
                event.c.rule_id == rule_id, event.c.active_key.is_not(None)
            )
        )
        .scalars()
        .all()
    )
    actions = []
    for event_id in rows:
        bind.execute(
            sa.update(request)
            .where(request.c.event_id == event_id, request.c.status == "pending")
            .values(
                status="cancelled",
                review_note="异常已自行恢复，申请自动取消",
                reviewed_at=now,
            )
        )
        bind.execute(
            sa.update(event)
            .where(event.c.id == event_id)
            .values(
                detection_status="recovered",
                closed_reason="rule_deleted",
                active_key=None,
                disposition="open",
                recovered_at=now,
                updated_at=now,
            )
        )
        actions.append(
            {
                "id": uuid4(),
                "event_id": event_id,
                "action": "recovered",
                "actor": "系统检测",
                "details": {"reason": "rule_deleted"},
                "created_at": now,
            }
        )
    return actions


def _collapse_duplicates() -> int:
    if context.is_offline_mode():
        raise RuntimeError(
            "0026 含数据回填，需联机执行：--sql 导出脚本拿不到这张表的历史行"
        )
    bind = op.get_bind()
    tables = _tables()
    rule = tables["rule"]
    rows = bind.execute(sa.select(rule).where(rule.c.status != "deleted")).mappings().all()
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (row["detector_type"], row["scope_type"], row["scope_value"]), []
        ).append(row)
    removed = 0
    audits: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda row: (row["created_at"], str(row["id"])))
        keeper, duplicates = items[0], items[1:]
        now = _now()
        # 保留最早一条，但别把检测静默关掉：重复行里有启用中的，保留行也启用。
        # 这也是状态变更，同样留审计（否则与下面的删除行不对称）。
        if keeper["status"] != "enabled" and any(
            row["status"] == "enabled" for row in duplicates
        ):
            keeper_version = int(keeper["version"]) + 1
            bind.execute(
                sa.update(rule)
                .where(rule.c.id == keeper["id"])
                .values(
                    status="enabled",
                    version=keeper_version,
                    change_reason=_ENABLED_REASON,
                    updated_by=_ACTOR,
                    updated_at=now,
                )
            )
            audits.append(
                {
                    "id": uuid4(),
                    "rule_id": keeper["id"],
                    "action": "enabled",
                    "version": keeper_version,
                    "before": _snapshot(
                        keeper, status=keeper["status"], version=int(keeper["version"])
                    ),
                    "after": _snapshot(
                        keeper, status="enabled", version=keeper_version
                    ),
                    "reason": _ENABLED_REASON,
                    "operator": _ACTOR,
                    "created_at": now,
                }
            )
        for row in duplicates:
            actions.extend(_close_rule_events(bind, tables, row["id"], now))
            version = int(row["version"]) + 1
            bind.execute(
                sa.update(rule)
                .where(rule.c.id == row["id"])
                .values(
                    status="deleted",
                    version=version,
                    change_reason=_REASON,
                    updated_by=_ACTOR,
                    updated_at=now,
                )
            )
            audits.append(
                {
                    "id": uuid4(),
                    "rule_id": row["id"],
                    "action": "deleted",
                    "version": version,
                    "before": _snapshot(row, status=row["status"], version=int(row["version"])),
                    "after": _snapshot(row, status="deleted", version=version),
                    "reason": _REASON,
                    "operator": _ACTOR,
                    "created_at": now,
                }
            )
            removed += 1
    if audits:
        op.bulk_insert(tables["audit"], audits)
    if actions:
        op.bulk_insert(tables["action"], actions)
    return removed


def _now() -> datetime:
    value = datetime.now(UTC)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def upgrade() -> None:
    _collapse_duplicates()
    if op.get_bind().dialect.name == "mysql":
        # MySQL 不能索引表达式，用虚拟生成列承载"NULL 归一"与"删除行不参与唯一性"。
        op.execute(
            "ALTER TABLE anomaly_rule ADD COLUMN scope_value_key VARCHAR(256) "
            "GENERATED ALWAYS AS (COALESCE(scope_value, '')) VIRTUAL"
        )
        op.execute(
            "ALTER TABLE anomaly_rule ADD COLUMN is_active INT "
            "GENERATED ALWAYS AS (CASE WHEN status = 'deleted' THEN NULL ELSE 1 END) VIRTUAL"
        )
        op.create_index(
            _INDEX,
            "anomaly_rule",
            ["detector_type", "scope_type", "scope_value_key", "is_active"],
            unique=True,
        )
        return
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX} ON anomaly_rule "
        "(detector_type, scope_type, COALESCE(scope_value, '')) "
        "WHERE status <> 'deleted'"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.drop_index(_INDEX, table_name="anomaly_rule")
        op.drop_column("anomaly_rule", "is_active")
        op.drop_column("anomaly_rule", "scope_value_key")
        return
    op.execute(f"DROP INDEX {_INDEX}")
