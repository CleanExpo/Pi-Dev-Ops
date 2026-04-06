$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "  Pi CEO - Solo DevOps Tool" -ForegroundColor DarkYellow
Write-Host "  http://127.0.0.1:7777" -ForegroundColor Green
Write-Host "  Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""
pip install fastapi uvicorn websockets python-multipart --quiet 2>$null
Set-Location $PSScriptRoot
python -m uvicorn server.main:app --host 127.0.0.1 --port 7777 --log-level info --no-access-log
