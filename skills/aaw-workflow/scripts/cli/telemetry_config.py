"""Telemetry configuration: upload switch, server rules and snapshot file filters.

Precedence (highest wins): AAW_TELEMETRY_ENABLED env (switch only) > project
.aaw/telemetry.yaml > server-delivered rules (GET /api/v1/telemetry/config,
disk-cached) > built-in yaml shipped with the CLI.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import yaml

BUILTIN_CONFIG = Path(__file__).parent / "telemetry_config.yaml"
PROJECT_CONFIG_RELATIVE = Path(".aaw") / "telemetry.yaml"
SERVER_CONFIG_TTL_SECONDS = 3600
SERVER_CONFIG_TIMEOUT_SECONDS = 2.0

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class TelemetryConfigError(Exception):
    pass


@dataclass(frozen=True)
class TelemetryConfig:
    enabled: bool
    max_file_bytes: int
    excluded_dirs: tuple[str, ...]
    excluded_suffixes: frozenset[str]

    def excluded_dir(self, name: str) -> str | None:
        """Return the configured directory that excludes `name`, if any."""
        lowered = name.lower()
        for directory in self.excluded_dirs:
            if lowered.startswith(directory + "/"):
                return directory
        return None

    def is_suffix_excluded(self, name: str) -> bool:
        """Snapshot-stage suffix exclusion (docs, logs, images, fonts...).

        A hit keeps the file out of D0/D1 entirely: never read, never
        diffed, never counted. Flagged as suffix_file_excluded so the
        exclusion stays observable.
        """
        return Path(name).suffix.lower() in self.excluded_suffixes


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text("utf-8")) or {}
    except OSError as exc:
        raise TelemetryConfigError(f"Unable to read telemetry config {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TelemetryConfigError(f"Unable to parse telemetry config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TelemetryConfigError(f"Telemetry config {path} must be a mapping")
    return raw


def _string_list(value: Any, path: Path, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TelemetryConfigError(f"Telemetry config {path} key filters.{key} must be a list of strings")
    return value


def _normalize_dirs(values: list[str], path: Path) -> tuple[list[str], list[str]]:
    """Split configured directories into additions and removals (`!` prefix)."""
    additions: list[str] = []
    removals: list[str] = []
    for raw in values:
        value = raw.strip()
        if not value:
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs must not contain an empty entry"
            )
        target = removals if value.startswith("!") else additions
        remainder = value[1:].strip() if value.startswith("!") else value
        if not remainder:
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs entry {raw!r} has an empty directory after '!'"
            )
        if remainder.startswith(("/", "\\")) or ":" in remainder:
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs entry {raw!r} must be a relative path"
            )
        normalized = remainder.replace("\\", "/").strip("/").lower()
        if not normalized:
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs entry {raw!r} is not a valid directory"
            )
        if normalized.startswith("!"):
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs entry {raw!r} must not start with '!!'"
            )
        if ".." in normalized.split("/"):
            raise TelemetryConfigError(
                f"Telemetry config {path} key filters.excluded_dirs entry {raw!r} must not contain '..'"
            )
        target.append(normalized)
    return additions, removals


def _env_override() -> bool | None:
    raw = os.getenv("AAW_TELEMETRY_ENABLED")
    if raw is None or not raw.strip():
        return None
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise TelemetryConfigError(
        f"Environment variable AAW_TELEMETRY_ENABLED has an invalid value {raw!r}; "
        "use one of 1/true/yes/on or 0/false/no/off"
    )


@lru_cache(maxsize=None)
def _load_config_cached(root: Path, server_filters_key: str) -> TelemetryConfig:
    server_filters = _decode_server_filters(server_filters_key)
    if not BUILTIN_CONFIG.is_file():
        raise TelemetryConfigError(f"Built-in telemetry config is missing: {BUILTIN_CONFIG}")
    builtin = _load_yaml(BUILTIN_CONFIG)
    enabled = builtin.get("enabled")
    filters = builtin.get("filters")
    if not isinstance(filters, dict):
        raise TelemetryConfigError(f"Telemetry config {BUILTIN_CONFIG} key filters must be a mapping")
    filters = dict(filters)
    source = {"enabled": BUILTIN_CONFIG, "filters": BUILTIN_CONFIG}

    # Server-delivered rules sit between the builtin yaml and the project
    # config: every key they carry replaces the builtin default wholesale.
    if server_filters is None:
        server_filters = _server_filters_cached()
    if server_filters:
        if not isinstance(server_filters, dict):
            raise TelemetryConfigError("Server telemetry filters must be a mapping")
        filters.update(server_filters)
        source["filters"] = "server"

    project_path = root / PROJECT_CONFIG_RELATIVE
    if project_path.is_file():
        project = _load_yaml(project_path)
        if "enabled" in project:
            enabled = project["enabled"]
            source["enabled"] = project_path
        if "filters" in project:
            project_filters = project["filters"]
            if not isinstance(project_filters, dict):
                raise TelemetryConfigError(f"Telemetry config {project_path} key filters must be a mapping")
            filters.update(project_filters)
            source["filters"] = project_path

    environment = _env_override()
    if environment is not None:
        enabled = environment
    elif not isinstance(enabled, bool):
        raise TelemetryConfigError(f"Telemetry config {source['enabled']} key enabled must be a boolean")

    filters_path = source["filters"]
    max_file_bytes = filters.get("max_file_bytes")
    if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
        raise TelemetryConfigError(
            f"Telemetry config {filters_path} key filters.max_file_bytes must be a positive integer"
        )
    # 后缀排除（快照阶段生效）。历史上有 diff_/snapshot_ 两个旧键：任一旧键
    # 出现即视为旧写法，两个键的值（缺省回落旧内置默认）合并成新键语义并
    # 覆盖内置新键；新配置（含服务端）只写 excluded_suffixes。
    legacy_keys = ("diff_excluded_suffixes", "snapshot_excluded_suffixes")
    if any(key in filters for key in legacy_keys):
        legacy_defaults = {
            "diff_excluded_suffixes": [".md", ".markdown", ".mdown", ".mkd", ".log"],
        }
        suffix_values = []
        for legacy_key in legacy_keys:
            if legacy_key in filters:
                suffix_values.extend(
                    _string_list(filters.get(legacy_key), filters_path, "excluded_suffixes")
                )
            else:
                suffix_values.extend(legacy_defaults.get(legacy_key, []))
        suffix_values = list(dict.fromkeys(suffix_values))
    else:
        suffix_values = _string_list(
            filters.get("excluded_suffixes"), filters_path, "excluded_suffixes"
        )
    builtin_dirs_add, builtin_dirs_remove = _normalize_dirs(
        _string_list(builtin["filters"].get("excluded_dirs"), BUILTIN_CONFIG, "excluded_dirs"),
        BUILTIN_CONFIG,
    )
    server_dirs_add: list[str] = []
    server_dirs_remove: list[str] = []
    if isinstance(server_filters, dict) and server_filters.get("excluded_dirs"):
        server_dirs_add, server_dirs_remove = _normalize_dirs(
            _string_list(server_filters["excluded_dirs"], "server-config", "excluded_dirs"),
            Path("server-config"),
        )
    project_dirs_add, project_dirs_remove = [], []
    if project_path.is_file():
        project_filters = project.get("filters")
        if isinstance(project_filters, dict) and "excluded_dirs" in project_filters:
            project_dirs_add, project_dirs_remove = _normalize_dirs(
                _string_list(project_filters["excluded_dirs"], project_path, "excluded_dirs"),
                project_path,
            )
    excluded_dirs = (
        set(builtin_dirs_add) | set(server_dirs_add) | set(project_dirs_add)
    ) - (
        set(builtin_dirs_remove) | set(server_dirs_remove) | set(project_dirs_remove)
    )
    return TelemetryConfig(
        enabled=enabled,
        max_file_bytes=max_file_bytes,
        excluded_dirs=tuple(sorted(excluded_dirs)),
        excluded_suffixes=frozenset(suffix.lower() for suffix in suffix_values),
    )


def load_config(
    root: Path,
    server_filters: dict[str, Any] | None = None,
) -> TelemetryConfig:
    """Load the effective telemetry config (cached per root + server rules).

    ``server_filters`` is normally omitted, which triggers a live pull from
    the server (with disk-cache fallback). Tests inject rules explicitly and
    can pass ``server_filters={}`` to disable the server layer entirely.
    """
    key = (
        json.dumps(server_filters, sort_keys=True, ensure_ascii=False)
        if server_filters is not None
        else ""
    )
    return _load_config_cached(root, key)


def _decode_server_filters(key: str) -> dict[str, Any] | None:
    if key == "":
        return _server_filters_cached()
    return json.loads(key)


def _server_filters_cached() -> dict[str, Any] | None:
    """Fetch server filter rules once per process; fall back to disk cache.

    Never raises: a config pull failure must not break telemetry. Returns
    None when neither the server nor a usable cache is available (the builtin
    yaml then provides the defaults).
    """
    endpoint = os.getenv("AAW_TELEMETRY_ENDPOINT", "").rstrip("/")
    if not endpoint:
        return None
    cache_dir = Path.home() / ".aaw" / "telemetry"
    cache_path = cache_dir / f"server-config-{abs(hash(endpoint)) & 0xFFFFFF:x}.json"
    now = time.time()
    try:
        payload = _fetch_server_config(endpoint)
    except Exception:
        payload = None
    if payload is not None and isinstance(payload.get("filters"), dict):
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"fetched_at": now, "filters": payload["filters"]}),
                encoding="utf-8",
            )
        except OSError:
            pass
        return payload["filters"]
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if now - float(cached.get("fetched_at", 0)) <= SERVER_CONFIG_TTL_SECONDS:
            filters = cached.get("filters")
            if isinstance(filters, dict):
                return filters
    except (OSError, ValueError, TypeError):
        pass
    return None


def _fetch_server_config(endpoint: str) -> dict[str, Any] | None:
    request = Request(f"{endpoint}/api/v1/telemetry/config", method="GET")
    with urlopen(request, timeout=SERVER_CONFIG_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))
