"""Health routes: /health, /api/health/vercel, Claude CLI poll, static files (RA-937)."""
import asyncio
import datetime
import hmac
import os
import logging
import time

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..app_factory import app, _resilient
from ..auth import require_auth, verify_session_token
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
    # RA-1003 + RA-1463: /health accepts either
    #   (a) Authorization: Bearer <TAO_PASSWORD>  — designed for external
    #       uptime monitors (UptimeRobot etc.) that can set a fixed bearer,
    #   (b) the signed `tao_session` cookie — set by the Vercel dashboard
    #       proxy (/api/pi-ceo/health) after it logs in with PI_CEO_PASSWORD,
    #   (c) a session-token Bearer for the same cookie value.
    #
    # If none of the above authenticate, return the minimal `{status:"ok"}`
    # shape with no internal details. Dashboard Overview falls back gracefully
    # on that shape but the full payload is what's useful.
    tao_password = os.environ.get("TAO_PASSWORD", "")
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    cookie_token = request.cookies.get("tao_session", "")

    authed = False
    if bearer and tao_password and hmac.compare_digest(bearer, tao_password):
        authed = True
    elif bearer and verify_session_token(bearer):
        authed = True
    elif cookie_token and verify_session_token(cookie_token):
        authed = True

    if tao_password and not authed:
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
    # ISO8601 UTC timestamp of last successful autonomy poll tick, or null if none yet.
    # Required by CLAUDE.md: "/health must surface … timestamp of last successful tick."
    last_tick: str | None = (
        datetime.datetime.fromtimestamp(last_poll_at, tz=datetime.timezone.utc).isoformat()
        if last_poll_at else None
    )

    # Swarm state — read env at request time (not module load) so Railway
    # restart-for-env-change takes effect immediately. The dashboard Overview
    # reads these as optional fields and falls back to "Active" when absent.
    swarm_enabled = os.environ.get("TAO_SWARM_ENABLED", "1") not in ("0", "false", "False", "")
    swarm_shadow = os.environ.get("TAO_SWARM_SHADOW", "0") not in ("0", "false", "False", "")

    # Pi-SEO scheduler gate — RA-1469. The cron loop fires every 60s but
    # `cron_triggers._fire_scan_trigger` and `_fire_monitor_trigger` skip
    # silently when PI_SEO_ACTIVE=0 (the default). When the flag is off,
    # the scheduler appears alive but no scans/monitors ever fire — the
    # exact failure mode that produced 161h of silent skipping pre-fix.
    # Surface it on /health so the watchdog (and operator dashboards) can
    # see "scheduler armed: false" instead of guessing at Railway env state.
    pi_seo_active = os.environ.get("PI_SEO_ACTIVE", "0") == "1"

    healthy = disk_free_gb is not None
    payload = {
        "status":           "ok" if healthy else "degraded",
        "uptime_s":         uptime_s,
        "sessions":         {"active": active, "total": total, "max": config.MAX_CONCURRENT_SESSIONS},
        "claude_cli":       _claude_ok,
        "anthropic_key":    anthropic_key_ok,
        # linear_key kept for dashboard backward-compat (CeoHealthPanel.tsx, overview/page.tsx)
        "linear_key":       linear_key_ok,
        # linear_api_key is the canonical name per CLAUDE.md ("Always surface linear_api_key: bool")
        "linear_api_key":   linear_key_ok,
        "autonomy": {
            "enabled":                 autonomy_enabled,
            "armed":                   autonomy_armed,
            "poll_count":              poll_count,
            # last_tick: ISO8601 UTC of last poll, null if poller has never fired.
            # CLAUDE.md: "/health must surface … timestamp of last successful tick."
            "last_tick":               last_tick,
            "seconds_since_last_poll": seconds_since_last_poll,
        },
        "disk_free_gb":     disk_free_gb,
        "version":          "1.0.0",
        "vercel_token":     bool(config.VERCEL_TOKEN),
        "swarm_enabled":    swarm_enabled,
        "swarm_shadow":     swarm_shadow,
        "pi_seo_active":    pi_seo_active,
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)


@app.get("/api/integrations/health")
async def integrations_health():
    """RA-1293 — Integration health snapshot.

    Public (no auth) so the dashboard can render it without a session, and so
    `/health` consumers can flag degraded auth state without credentials. The
    snapshot contains no secrets — only probe names, ok/fail, and short detail
    strings like 'HTTP 401' or 'last_poll_age_s=370'.
    """
    from ..integration_health import get_snapshot
    return get_snapshot()


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
