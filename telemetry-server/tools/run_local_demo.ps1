# 本地演示环境一键启动（mock 归因引擎 + 遥测服务 + 门户）
# 用法：在 telemetry-server 目录执行  .\.venv\Scripts\python.exe -m uvicorn ... 见文件末尾
# 或直接：  powershell -File tools\run_local_demo.ps1
# 预置数据：python tools\seed_demo_data.py （服务启动后执行一次；数据库已存在数据则跳过）

$root = $PSScriptRoot | Split-Path
$demo = Join-Path $root "data\local-demo"

$env:AAW_TELEMETRY_DATABASE_URL                = "sqlite:///$($demo -replace '\\','/')/telemetry.db"
$env:AAW_TELEMETRY_OBJECT_STORAGE_DIR          = Join-Path $demo "objects"
$env:AAW_TELEMETRY_LOG_DIRECTORY               = Join-Path $demo "logs"
$env:AAW_TELEMETRY_RELEASE_DIR                 = Join-Path $demo "releases"
$env:AAW_TELEMETRY_ATTRIBUTION_SERVICE_URL     = "http://127.0.0.1:8010"
$env:AAW_TELEMETRY_ATTRIBUTION_SCAN_INTERVAL_SECONDS = "60"

$py = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "启动 mock 归因引擎 :8010"
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","tools.mock_engine:app","--port","8010","--no-access-log"

Write-Host "启动遥测服务+门户  :8000"
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","tools.local_demo:app","--port","8000","--no-access-log"

Write-Host ""
Write-Host "就绪后："
Write-Host "  管理台   http://127.0.0.1:8000/admin"
Write-Host "  采纳看板 http://127.0.0.1:8000/portal/bright.html"
Write-Host "  预置数据 $py tools\seed_demo_data.py"
