"""Server-managed snapshot/diff filter rules with version history.

The filter semantics live in the CLI (``telemetry_config.py``) — directory
exclusion anchoring and suffix exclusion. The server stores a ``filters``
mapping with the same keys as the CLI's builtin yaml, validates every entry
with the same strictness the CLI applies to its own config files, and
answers CLI pulls through the public ``/api/v1/telemetry/config`` endpoint.
Every save inserts a new version row; the table is append-only and doubles
as change history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import TelemetryFilterConfig

FILTER_KEYS = (
    "max_file_bytes",
    "excluded_dirs",
    "excluded_suffixes",
)
# 旧配置写法；读取时并入 excluded_suffixes，保存时统一写新键。
LEGACY_SUFFIX_KEYS = ("diff_excluded_suffixes", "snapshot_excluded_suffixes")

_MAX_FILE_BYTES_RANGE = (1, 1024 * 1024 * 1024)
_MAX_LIST_ENTRIES = 512
_MAX_STRING_BYTES = 2048


def _now() -> datetime:
    value = datetime.now(UTC)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def _string_list(value, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ApiError(422, "FILTER_INVALID", f"filters.{key} 必须是字符串数组")
    if len(value) > _MAX_LIST_ENTRIES:
        raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目数超过 {_MAX_LIST_ENTRIES}")
    return value


def _validate_dirs(values: list[str], key: str) -> list[str]:
    for raw in values:
        value = raw.strip()
        if not value:
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目不能为空")
        target = value[1:].strip() if value.startswith("!") else value
        if not target:
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目 {raw!r} 在 '!' 后没有目录")
        if target.startswith(("/", "\\")) or ":" in target:
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目 {raw!r} 必须是相对路径")
        if ".." in target.replace("\\", "/").strip("/").split("/"):
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目 {raw!r} 不能包含 '..'")


def _validate_suffixes(values: list[str], key: str) -> list[str]:
    for value in values:
        if not value.startswith(".") or len(value) < 2 or value.count(".") > 1:
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目 {value!r} 必须是形如 '.png' 的后缀")


def validate_filters(filters: dict) -> dict:
    """Validate a full filters mapping; returns the canonical dict or raises.

    Accepts the legacy ``diff_excluded_suffixes`` / ``snapshot_excluded_suffixes``
    keys (merged into ``excluded_suffixes``) so older clients keep working.
    """
    if not isinstance(filters, dict):
        raise ApiError(422, "FILTER_INVALID", "filters 必须是对象")
    filters = _merge_legacy_suffix_keys(filters)
    unknown = set(filters) - set(FILTER_KEYS)
    if unknown:
        raise ApiError(422, "FILTER_INVALID", f"filters 含未知键: {', '.join(sorted(unknown))}")

    max_file_bytes = filters.get("max_file_bytes")
    if (
        isinstance(max_file_bytes, bool)
        or not isinstance(max_file_bytes, int)
        or not _MAX_FILE_BYTES_RANGE[0] <= max_file_bytes <= _MAX_FILE_BYTES_RANGE[1]
    ):
        raise ApiError(
            422,
            "FILTER_INVALID",
            f"filters.max_file_bytes 必须是 {_MAX_FILE_BYTES_RANGE[0]}~{_MAX_FILE_BYTES_RANGE[1]} 之间的整数",
        )

    dirs = _string_list(filters.get("excluded_dirs"), "excluded_dirs")
    _validate_dirs(dirs, "excluded_dirs")
    suffixes = _string_list(filters.get("excluded_suffixes"), "excluded_suffixes")
    _validate_bounded(suffixes, "excluded_suffixes")
    _validate_suffixes(suffixes, "excluded_suffixes")
    return {key: filters[key] for key in FILTER_KEYS}


def _merge_legacy_suffix_keys(filters: dict) -> dict:
    """Fold the two legacy suffix keys into the unified one (dedup, keep order)."""
    legacy = [key for key in LEGACY_SUFFIX_KEYS if key in filters]
    if not legacy:
        return filters
    merged = {k: v for k, v in filters.items() if k not in LEGACY_SUFFIX_KEYS}
    values: list[str] = list(filters.get("excluded_suffixes") or [])
    for key in legacy:
        values.extend(filters[key] or [])
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    merged["excluded_suffixes"] = deduped
    return merged


def _validate_bounded(values: list[str], key: str) -> None:
    for value in values:
        if not value or len(value.encode("utf-8")) > _MAX_STRING_BYTES:
            raise ApiError(422, "FILTER_INVALID", f"filters.{key} 条目为空或超过 {_MAX_STRING_BYTES} 字节")


@dataclass(frozen=True)
class FilterDecision:
    path: str
    excluded: bool
    rule: str
    detail: str


def evaluate_filters(filters: dict, paths: list[str]) -> list[FilterDecision]:
    """Run the snapshot-stage decision chain over candidate paths.

    This mirrors the CLI's ``TelemetryStore._worktree_files`` order: internal
    dir → excluded_dirs → suffixes. The size check is skipped (the server
    never sees file bytes); that stage reports as not excluded, which is
    what an admin needs to see here.
    """
    excluded_dirs = sorted(
        {value.lower() for value in filters.get("excluded_dirs", []) if not value.startswith("!")},
    )
    excluded_suffixes = {value.lower() for value in filters.get("excluded_suffixes", [])}

    decisions: list[FilterDecision] = []
    for raw in paths:
        path = raw.replace("\\", "/").strip("/")
        if path.startswith(".aaw/telemetry/"):
            decisions.append(FilterDecision(path, True, "internal", ".aaw/telemetry/ 内部目录"))
            continue
        directory = next((d for d in excluded_dirs if path.lower().startswith(d + "/")), None)
        if directory is not None:
            decisions.append(FilterDecision(path, True, "dir_excluded", directory))
            continue
        suffix = next(
            (s for s in excluded_suffixes if path.lower().endswith(s)),
            None,
        )
        if suffix is not None:
            decisions.append(FilterDecision(path, True, "suffix_excluded", suffix))
            continue
        decisions.append(FilterDecision(path, False, "included", ""))
    return decisions


class TelemetryFilterService:
    def __init__(self, session: Session):
        self.session = session

    def current(self) -> TelemetryFilterConfig | None:
        return self.session.scalar(
            select(TelemetryFilterConfig).order_by(TelemetryFilterConfig.version.desc()).limit(1)
        )

    def get_current(self) -> dict:
        row = self.current()
        if row is None:
            raise ApiError(404, "FILTER_CONFIG_NOT_FOUND", "尚未保存过上报过滤配置")
        return {
            "version": row.version,
            "filters": row.filters,
            "updated_by": row.updated_by,
            "updated_at": int(row.updated_at.timestamp() * 1000),
        }

    def history(self, limit: int = 50) -> dict:
        rows = self.session.scalars(
            select(TelemetryFilterConfig)
            .order_by(TelemetryFilterConfig.version.desc())
            .limit(limit)
        ).all()
        return {
            "items": [
                {
                    "version": row.version,
                    "filters": row.filters,
                    "updated_by": row.updated_by,
                    "updated_at": int(row.updated_at.timestamp() * 1000),
                }
                for row in rows
            ]
        }

    def save(self, filters: dict, actor: str) -> dict:
        validated = validate_filters(filters)
        latest = self.current()
        next_version = (latest.version + 1) if latest else 1
        row = TelemetryFilterConfig(
            version=next_version,
            filters=validated,
            updated_by=actor,
            updated_at=_now(),
        )
        self.session.add(row)
        self.session.commit()
        return {
            "version": row.version,
            "filters": row.filters,
            "updated_by": row.updated_by,
            "updated_at": int(row.updated_at.timestamp() * 1000),
        }

    def preview(self, filters: dict, paths: list[str]) -> dict:
        validated = validate_filters(filters)
        return {
            "filters": validated,
            "items": [
                {
                    "path": decision.path,
                    "excluded": decision.excluded,
                    "rule": decision.rule,
                    "detail": decision.detail,
                }
                for decision in evaluate_filters(validated, paths)
            ],
        }
