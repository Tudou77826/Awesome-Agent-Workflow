"""本地演示启动器：遥测服务 + 门户静态资源同源伺服。

生产环境门户由 nginx 伺服（telemetry-front/nginx.portal.conf）；本地预览时
用本模块把 portal 目录挂到 /portal，运营后台（/admin）里引用的
/portal/vendor/fonts.css 才能加载。

用法（在 telemetry-server 目录）：
  set AAW_TELEMETRY_DATABASE_URL=sqlite:///data/local-demo/telemetry.db
  ... 其余环境变量见 tools/run_local_demo.ps1
  uvicorn tools.local_demo:app --port 8000
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from aaw_telemetry.config import get_settings
from aaw_telemetry.main import create_app

settings = get_settings()
app = create_app(settings)

_PORTAL_DIR = Path(__file__).resolve().parents[2] / "telemetry-front" / "portal"
if _PORTAL_DIR.is_dir():
    app.mount("/portal", StaticFiles(directory=_PORTAL_DIR, html=True), name="portal")


@app.on_event("startup")
async def _seed_telemetry_filters() -> None:
    """首启时把 CLI 内置 yaml 灌成 v1，运营后台「上报过滤」页开箱即有当前值。"""
    import yaml
    from sqlalchemy import select

    from aaw_telemetry.database import build_session_factory
    from aaw_telemetry.models import TelemetryFilterConfig
    from aaw_telemetry.services.telemetry_filters import validate_filters

    builtin = (
        Path(__file__).resolve().parents[2]
        / "skills/aaw-workflow/scripts/cli/telemetry_config.yaml"
    )
    if not builtin.is_file():
        return
    filters = yaml.safe_load(builtin.read_text(encoding="utf-8"))["filters"]
    with build_session_factory(app.state.engine)() as session:
        if session.scalar(select(TelemetryFilterConfig).limit(1)) is None:
            session.add(
                TelemetryFilterConfig(
                    version=1,
                    filters=validate_filters(filters),
                    updated_by="本地演示种子",
                    updated_at=datetime.now(UTC),
                )
            )
            session.commit()


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/portal/bright.html")
