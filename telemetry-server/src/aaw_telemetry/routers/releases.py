from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..config import Settings
from ..errors import ApiError
from ..schemas import ClientReleaseResponse
from ..services.version_ops import find_latest_release

logger = logging.getLogger("aaw_telemetry.client.release")

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def build_releases_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/client", tags=["client"])

    @router.get(
        "/release",
        response_model=ClientReleaseResponse,
        summary="查询最新客户端发布版本",
        description=(
            "扫描配置的发布目录，返回版本号最大的 `aaw-skills-<version>.zip`。"
            "目录未配置、不存在或没有合法发布包时 `latest_version` 为 null。"
        ),
    )
    def latest_release() -> ClientReleaseResponse:
        latest = find_latest_release(settings.release_dir)
        if latest is None:
            logger.info(
                "客户端检查更新，但当前没有可用发布包",
                extra={"event": "client.release_checked", "found": False},
            )
            return ClientReleaseResponse(latest_version=None)
        version, path = latest
        stat = path.stat()
        released_at = datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0)
        logger.info(
            f"客户端检查更新，当前最新版本为 {version}",
            extra={
                "event": "client.release_checked",
                "found": True,
                "version": version,
                "size_bytes": stat.st_size,
            },
        )
        return ClientReleaseResponse(
            latest_version=version,
            file_name=path.name,
            size_bytes=stat.st_size,
            released_at=released_at.isoformat().replace("+00:00", "Z"),
        )

    @router.get(
        "/releases/{version}/download/{file_name}",
        summary="下载指定版本的客户端发布包",
        description=(
            "`version` 必须是严格三段版本，且 `file_name` 必须精确等于 "
            "`aaw-skills-{version}.zip`；不匹配或文件不存在时返回 404。"
        ),
    )
    def download_release(version: str, file_name: str) -> FileResponse:
        expected = f"aaw-skills-{version}.zip"
        if VERSION_PATTERN.fullmatch(version) is None or file_name != expected:
            logger.warning(
                "客户端请求的发布包名称或版本不合法，已拒绝下载",
                extra={
                    "event": "client.release_download_failed",
                    "error_code": "RELEASE_NOT_FOUND",
                },
            )
            raise ApiError(404, "RELEASE_NOT_FOUND", "release does not exist")
        release_dir = settings.release_dir
        path = release_dir / expected if release_dir is not None else None
        if path is None or not path.is_file():
            logger.warning(
                "客户端请求的发布包不存在，无法开始下载",
                extra={
                    "event": "client.release_download_failed",
                    "error_code": "RELEASE_NOT_FOUND",
                    "version": version,
                },
            )
            raise ApiError(404, "RELEASE_NOT_FOUND", "release does not exist")
        logger.info(
            f"客户端开始下载 {version} 发布包",
            extra={
                "event": "client.release_download_started",
                "version": version,
                "size_bytes": path.stat().st_size,
            },
        )
        return FileResponse(path, filename=expected)

    return router
