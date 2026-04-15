"""Health routes: /health, /api/health/vercel, Claude CLI poll, static files (RA-937)."""
import asyncio
import hmac
import os
import logging
import time

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..app_factory import app, _resilient
from ..auth import require_auth
from ..sessions import _sessions
from ..vercel_monitor import check_deployment_drift
from .. import config

log = logging.getLogger("pi-ceo.main")

_START_TIME = time.time()
_claude_ok: bool = False


async def _poll_claude_cli() -> None:
    """Check Claude CLI in background every 30s — never blocks health endpoint."""
    global _claude_ok
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                config.CLAUDE_CMD, "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
                _claude_ok = proc.returncode == 0
            except asyncio.TimeoutError:
                proc.kill()
                _claude_ok = False
        except Exception:
            _claude_ok = False
        await asyncio.sleep(30)


@app.on_event("startup")
async def _start_claude_poll():
    asyncio.create_task(_resilient(_poll_claude_cli, "claude_cli_poll"))


STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    p = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(p) if os.path.exists(p) else JSONResponse({"status": "Pi CEO running"})


@app.get("/health")
async def health(request: Request):
    # RA-1003: If TAO_PASSWORD is configured, require Authorization: Bearer <password>.
    # Unauthenticated callers receive a minimal response with no internal details.
    tao_password = os.environ.get("TAO_PASSWORD", "")
    if tao_password:
        auth_header = request.headers.get("Authorization", "")
        provided = auth_header[7:] if auth_header.startswith("Bearer ") else ""
        if not provided or not hmac.compare_digest(provided, tao_password):
            return JSONResponse({"status": "ok"}, status_code=200)

    uptime_s = int(time.time() - _START_TIME)
    active = sum(
        1 for s in _sessions.values()
        if getattr(s, "status", "") in ("created", "cloning", "building", "evaluating")
    )
    total = len(_sessions)

    disk_free_gb: float | None = None
    try:
        import shutil
        disk = shutil.disk_usage(config.WORKSPACE_ROOT)
        disk_free_gb = round(disk.free / 1e9, 1)
    except Exception:
        pass

    anthropic_key_ok = bool(config.ANTHROPIC_API_KEY)
    linear_key_ok    = bool(config.LINEAR_API_KEY)
    autonomy_enabled = bool(config.AUTONOMY_ENABLED)

    # Autonomy is considered "armed" only when the flag is on AND the key is present.
    autonomy_armed = autonomy_enabled and linear_key_ok

    from .. import autonomy as _autonomy
    last_poll_at = getattr(_autonomy, "_last_poll_at", 0.0) or 0.0
    poll_count   = getattr(_autonomy, "_poll_count", 0)
    seconds_since_last_poll = int(time.time() - last_poll_at) if last_poll_at else None

    healthy = disk_free_gb is not None
    payload = {
        "status":           "ok" if healthy else "degraded",
        "uptime_s":         uptime_s,
        "sessions":         {"active": active, "total": total, "max": config.MAX_CONCURRENT_SESSIONS},
        "claude_cli":       _claude_ok,
        "anthropic_key":    anthropic_key_ok,
        "linear_key":       linear_key_ok,
        "autonomy": {
            "enabled":                 autonomy_enabled,
            "armed":                   autonomy_armed,
            "poll_count":              poll_count,
            "seconds_since_last_poll": seconds_since_last_poll,
        },
        "disk_free_gb":     disk_free_gb,
        "version":          "1.0.0",
        "vercel_token": bool(config.VERCEL_TOKEN),
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)


@app.get("/api/health/vercel", dependencies=[Depends(require_auth)])
async def vercel_health():
    """RA-692 — Vercel deployment drift check."""
    result = check_deployment_drift()
    payload = {
        "degraded":               result.degraded,
        "drifted":                result.drifted,
        "deployment_state":       result.deployment_state,
        "deployment_url":         result.deployment_url,
        "latest_deployment_sha":  result.latest_deployment_sha,
        "head_sha":               result.head_sha,
        "error":                  result.error,
        "vercel_token_configured": bool(config.VERCEL_TOKEN),
    }
    status = 200 if not result.degraded else 503
    return JSONResponse(payload, status_code=status)
