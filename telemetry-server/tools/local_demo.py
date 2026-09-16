"""本地演示启动器：遥测服务 + 门户静态资源同源伺服。

生产环境门户由 nginx 伺服（telemetry-front/nginx.portal.conf）；本地预览时
用本模块把 portal 目录挂到 /portal，管理台（/admin）里引用的
/portal/vendor/fonts.css 才能加载。

用法（在 telemetry-server 目录）：
  set AAW_TELEMETRY_DATABASE_URL=sqlite:///data/local-demo/telemetry.db
  ... 其余环境变量见 tools/run_local_demo.ps1
  uvicorn tools.local_demo:app --port 8000
"""

from __future__ import annotations

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


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/portal/bright.html")
