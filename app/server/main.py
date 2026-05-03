"""Pi CEO — FastAPI entry point (RA-937).

This file is the thin assembler. All logic lives in focused modules:
  app_factory.py  — app object, middleware, startup/shutdown hooks
  models.py       — Pydantic request models
  routes/         — one file per concern

Public contract (Dockerfile + Railway reference `app.server.main:app`):
  `from app.server.main import app` must always work.
"""
from .app_factory import app  # noqa: F401  (re-exported for uvicorn / callers)

from .routes import auth, sessions, webhooks, triggers, scan_monitor, pipeline, utils, telegram_proxy, mission_control, phone, swarm, margot, cost_report
# health registers its routes directly on `app` via @app.get/@app.on_event decorators
from .routes import health  # noqa: F401

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(webhooks.router)
app.include_router(triggers.router)
app.include_router(scan_monitor.router)
app.include_router(pipeline.router)
app.include_router(utils.router)
app.include_router(telegram_proxy.router)
app.include_router(mission_control.router)
app.include_router(phone.router)
app.include_router(swarm.router)
app.include_router(margot.router)  # RA-1871
app.include_router(cost_report.router)  # RA-1909

__all__ = ["app"]
