"""FastAPI application factory for Pi CEO (RA-937).

Creates and configures the `app` object — middleware, startup/shutdown events.
Route registration happens in main.py (thin assembler).
"""
import asyncio
import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .sessions import restore_sessions, _sessions
from .gc import gc_loop
from .cron import cron_loop
from .autonomy import linear_todo_poller
from .agents.build_stall_watchdog import stall_watchdog_loop  # RA-1104
from .integration_health import integration_health_loop      # RA-1293
from . import config

log = logging.getLogger("pi-ceo.main")

# True when deployed on Railway (or any cloud with this env var set)
_IS_CLOUD = bool(
    os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("RENDER")
    or os.environ.get("FLY_APP_NAME")
)

# Allowed origins: local Next.js dev + Vercel deployments
# Append extra origins via TAO_ALLOWED_ORIGINS (comma-separated)
_extra = os.environ.get("TAO_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://pi-dev-ops.vercel.app",
    "https://dashboard-unite-group.vercel.app",
] + [o.strip() for o in _extra.split(",") if o.strip()]


_MAX_REQUEST_BODY = 10 * 1024 * 1024  # 10 MB — RA-1019


class RequestSizeLimit(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds _MAX_REQUEST_BODY (RA-1019)."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_REQUEST_BODY:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        return await call_next(request)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # RA-1016: 'unsafe-inline' removed from script-src. Next.js dashboard
            # must not rely on inline scripts — use external bundles only.
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss: https://*.vercel.app https://*.railway.app; "
            "img-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        return response


async def _resilient(coro_factory, name: str, restart_delay: float = 10.0):
    """Wrap a background coroutine with crash-recovery and auto-restart."""
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            log.info("Background task '%s' cancelled", name)
            return
        except Exception as exc:
            log.error(
                "Background task '%s' crashed: %s — restarting in %.0fs",
                name, exc, restart_delay, exc_info=True,
            )
            await asyncio.sleep(restart_delay)


app = FastAPI(title="Pi CEO", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(SecurityHeaders)
app.add_middleware(RequestSizeLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Cookie", "Authorization"],
)
# NOTE: TrustedHostMiddleware removed — Railway terminates TLS and proxies requests;
# restricting to 127.0.0.1 would block all cloud traffic.


@app.on_event("startup")
async def on_startup():
    restore_sessions()
    asyncio.create_task(_resilient(lambda: gc_loop(_sessions), "gc_loop"))
    asyncio.create_task(_resilient(cron_loop, "cron_loop"))
    asyncio.create_task(_resilient(linear_todo_poller, "linear_todo_poller"))
    asyncio.create_task(_resilient(stall_watchdog_loop, "stall_watchdog_loop"))  # RA-1104
    asyncio.create_task(_resilient(integration_health_loop, "integration_health_loop"))  # RA-1293
    if config.AUTONOMY_ENABLED:
        log.info("Autonomy poller enabled — polling Linear every 5 min for Todo issues")
    else:
        log.info("Autonomy poller DISABLED (TAO_AUTONOMY_ENABLED=0)")
    if not config.ANTHROPIC_API_KEY:
        log.warning(
            "ANTHROPIC_API_KEY is empty — Anthropic SDK calls will fail. "
            "If launched from a terminal running the claude CLI, start with: "
            "source .env.local && uvicorn ..."
        )
    if not config.WEBHOOK_SECRET:
        log.warning("TAO_WEBHOOK_SECRET not set — GitHub webhook endpoint is unprotected")
    if not config.LINEAR_WEBHOOK_SECRET:
        log.warning("TAO_LINEAR_WEBHOOK_SECRET not set — Linear webhook endpoint is unprotected")
    cache_status = "enabled" if config.ENABLE_PROMPT_CACHING_1H else "disabled"
    log.info("Prompt caching: %s (ENABLE_PROMPT_CACHING_1H)", cache_status)
    log.info("Pi CEO ready on %s:%s", config.HOST, config.PORT)


@app.on_event("shutdown")
async def on_shutdown():
    """Drain active sessions on SIGTERM (RA-521)."""
    active = [
        s for s in _sessions.values()
        if getattr(s, "status", "") in ("created", "cloning", "building", "evaluating")
    ]
    if active:
        log.info("Shutdown: draining %d active sessions", len(active))
        for session in active:
            session.status = "interrupted"
            proc = getattr(session, "process", None)
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
        await asyncio.sleep(2)
    log.info("Shutdown complete")
