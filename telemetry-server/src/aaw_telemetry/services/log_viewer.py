from __future__ import annotations

import re
from pathlib import Path

from ..errors import ApiError

LOG_FILES = ("server.log", "error.log", "access.log")
MAX_TAIL_BYTES = 2 * 1024 * 1024
MAX_LINES = 500

# 日志行以本地时间 "YYYY-MM-DD HH:MM:SS.mmm" 开头，时间窗按同宽前缀做字典序比较
_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_BOUND = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2})(?::(\d{2}))?)?$")


def _normalize_bound(value: str | None, *, is_end: bool) -> str | None:
    """把边界输入规整成与日志时间前缀同宽的 "YYYY-MM-DD HH:MM:SS"。"""
    if value is None or not value.strip():
        return None
    match = _BOUND.match(value.strip())
    if match is None:
        raise ApiError(
            400, "INVALID_FILTER", "时间格式须为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]"
        )
    date, minute, second = match.groups()
    if second is None:
        # 只给到分钟时，起点取该分钟头，终点取该分钟尾
        second = "59" if is_end else "00"
    return f"{date} {minute or '00:00'}:{second}"


def _filter_window(
    rows: list[str], since: str | None, until: str | None
) -> list[str]:
    kept: list[str] = []
    previous_kept = True
    for row in rows:
        if _TS_PREFIX.match(row):
            key = row[:19]
            keep = (since is None or key >= since) and (until is None or key <= until)
            previous_kept = keep
        else:
            # 无时间戳的行（如异常堆栈续行）跟随其所属的上一条日志
            keep = previous_kept
        if keep:
            kept.append(row)
    return kept


def describe_files(directory: Path) -> list[dict]:
    files = []
    for name in LOG_FILES:
        path = directory / name
        files.append(
            {
                "file": name,
                "size_bytes": path.stat().st_size if path.is_file() else 0,
                "available": path.is_file(),
            }
        )
    return files


def read_tail(
    directory: Path,
    file_name: str,
    *,
    lines: int,
    level: str | None = None,
    event: str | None = None,
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """Return the last matching lines of a whitelisted log file.

    Only a bounded tail window is ever read, so a rotated 100MB file costs the
    same as an empty one. Line filters are substring matches against the
    ``[LEVEL]`` marker and the ``event=`` field of the text format; the time
    window compares against the local timestamp prefix of each line.
    """
    if file_name not in LOG_FILES:
        raise ApiError(404, "LOG_FILE_UNKNOWN", f"未知日志文件 {file_name}")
    since_bound = _normalize_bound(since, is_end=False)
    until_bound = _normalize_bound(until, is_end=True)
    path = directory / file_name
    if not path.is_file():
        return {
            "file": file_name,
            "lines": [],
            "truncated": False,
            "size_bytes": 0,
            "scanned_bytes": 0,
        }
    size = path.stat().st_size
    start = max(0, size - MAX_TAIL_BYTES)
    with path.open("rb") as stream:
        stream.seek(start)
        chunk = stream.read()
    rows = chunk.decode("utf-8", errors="replace").splitlines()
    if start > 0 and rows:
        rows = rows[1:]  # the first row is likely cut in half
    if since_bound is not None or until_bound is not None:
        rows = _filter_window(rows, since_bound, until_bound)
    if level:
        marker = f"[{level.upper()}]"
        rows = [row for row in rows if marker in row]
    if event:
        rows = [row for row in rows if f"event={event}" in row]
    if query:
        needle = query.lower()
        rows = [row for row in rows if needle in row.lower()]
    truncated = start > 0 or len(rows) > lines
    return {
        "file": file_name,
        "lines": rows[-lines:],
        "truncated": truncated,
        "size_bytes": size,
        "scanned_bytes": len(chunk),
    }
