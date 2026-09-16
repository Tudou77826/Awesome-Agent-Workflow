from __future__ import annotations

import contextvars
import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class TextFormatter(logging.Formatter):
    """Readable narrative logs followed by searchable ``key=value`` fields."""

    _standard = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
    _sensitive = {
        "authorization",
        "cookie",
        "database_url",
        "file_sha256",
        "object_key",
        "password",
        "request_body",
        "sha256",
    }

    @staticmethod
    def _render_value(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        rendered = str(value)
        if not rendered or any(character.isspace() for character in rendered) or any(
            character in rendered for character in '"=\\'
        ):
            return json.dumps(rendered, ensure_ascii=False, separators=(",", ":"))
        return rendered

    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, UTC)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        )
        location = getattr(record, "location", None) or record.name
        if location.startswith("aaw_telemetry."):
            location = location.removeprefix("aaw_telemetry.")
        message = record.getMessage().replace("\r", "\\r").replace("\n", "\\n")
        business: list[str] = []
        request_field: str | None = None
        request_id = request_id_var.get()
        if request_id != "-":
            request_field = f"request_id={self._render_value(request_id)}"
        for key, value in record.__dict__.items():
            if (
                key not in self._standard
                and key.lower() not in self._sensitive
                and key != "location"
                and not key.startswith("_")
            ):
                business.append(f"{key}={self._render_value(value)}")
        # event 是人工排查时的主检索键，放最前；request_id 最长，垫到行尾
        fields = [field for field in business if field.startswith("event=")]
        fields += [field for field in business if not field.startswith("event=")]
        if request_field is not None:
            fields.append(request_field)
        rendered = f"{timestamp} [{record.levelname}] [{location}] {message}"
        if fields:
            rendered += " | " + " ".join(fields)
        if record.exc_info:
            rendered += "\n" + self.formatException(record.exc_info)
        return rendered


def _resolve_config_path(path: Path) -> Path:
    if path.is_absolute() or path.exists():
        return path
    candidate = Path(__file__).resolve().parents[2] / path
    return candidate if candidate.exists() else path


def configure_logging(
    config_file: Path,
    *,
    level: str | None = None,
    directory_override: Path | None = None,
) -> Path:
    path = _resolve_config_path(config_file)
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}

    configured_directory = Path(config.pop("log_directory", "logs"))
    log_directory = directory_override or configured_directory
    if not log_directory.is_absolute():
        log_directory = Path.cwd() / log_directory
    log_directory.mkdir(mode=0o750, parents=True, exist_ok=True)

    file_handlers = {"access_file", "server_file", "error_file"}
    for name in file_handlers:
        handler = config.get("handlers", {}).get(name)
        if handler is None:
            raise ValueError(f"logging config is missing handler {name!r}")
        handler["filename"] = str(log_directory / Path(handler["filename"]).name)
        handler["lock_file_directory"] = str(log_directory)
        log_file = Path(handler["filename"])
        log_file.touch(exist_ok=True)
        if os.name != "nt":
            log_file.chmod(0o640)

    if level is not None:
        normalized = level.upper()
        config["root"]["level"] = normalized
        config["handlers"]["console"]["level"] = normalized
        config["handlers"]["server_file"]["level"] = normalized
        config["loggers"]["aaw_telemetry.http.access"]["level"] = normalized

    logging.config.dictConfig(config)
    logging.captureWarnings(True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    return log_directory
