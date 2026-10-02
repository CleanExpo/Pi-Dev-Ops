"""TAO_PASSWORD must never be invented and logged, and diagnostics are not public.

Audit 2026-09-30 rank #8: with TAO_PASSWORD unset, config.py generated a
password and wrote it to the log (Railway keeps those logs), and
scripts/deploy_railway.sh generated one and printed its prefix. Several
diagnostic routes answered anyone on the internet.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]

# Runs config.py import in a clean interpreter: env files are hidden so a
# developer's .env.local cannot supply TAO_PASSWORD, and every log record is
# captured so the test can see exactly what would reach Railway's log.
_PROBE = r"""
import json, logging, pathlib, sys
_orig = pathlib.Path.is_file
pathlib.Path.is_file = lambda p: False if p.name in (".env", ".env.local") else _orig(p)
records = []
class _Cap(logging.Handler):
    def emit(self, r):
        records.append(r.getMessage())
logging.getLogger().addHandler(_Cap())
logging.getLogger().setLevel(logging.DEBUG)
try:
    from app.server import config
except SystemExit as exc:
    print(json.dumps({"exit": str(exc), "logs": records}))
    sys.exit(3)
print(json.dumps({"exit": None, "logs": records, "pw": config._raw_password}))
"""


def _import_config(extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("TAO_PASSWORD", "RAILWAY_ENVIRONMENT", "RENDER", "FLY_APP_NAME")}
    env["TAO_SESSION_SECRET"] = "test-session-secret-32-chars-xxxx"
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", _PROBE], cwd=_ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )


def test_railway_refuses_to_start_without_tao_password():
    proc = _import_config({"RAILWAY_ENVIRONMENT": "production"})
    assert proc.returncode == 3, proc.stdout + proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["exit"] == "TAO_PASSWORD not configured"


def test_no_log_line_can_carry_a_generated_password():
    proc = _import_config({})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    logs = "\n".join(out["logs"]) + proc.stderr
    assert "Generated one-time password" not in logs
    if out["pw"]:
        assert out["pw"] not in logs


def test_deploy_script_neither_generates_nor_prints_tao_password():
    script = (_ROOT / "scripts" / "deploy_railway.sh").read_text()
    for line in script.splitlines():
        if "TAO_PASSWORD" in line:
            assert "openssl" not in line and not line.lstrip().startswith("echo"), line


# --- routes -----------------------------------------------------------------

_GATED = [
    "/api/integrations/health",
    "/api/health/obsidian",
    "/api/health/full",
    "/api/health/ready",
    "/api/telegram/intake/status",
]


def _client() -> TestClient:
    from app.server.app_factory import app
    from app.server.routes import health  # noqa: F401 — registers /health on app
    from app.server.routes import health_full, health_ready, telegram_intake
    for r in (health_full.router, health_ready.router, telegram_intake.router):
        if not any(getattr(x, "path", None) in {p.path for p in r.routes} for x in app.routes):
            app.include_router(r)
    return TestClient(app)


@pytest.mark.parametrize("path", _GATED)
def test_diagnostic_route_rejects_anonymous(path):
    assert _client().get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/integrations/health", "/api/telegram/intake/status"])
def test_diagnostic_route_serves_a_session(path):
    from app.server.auth import create_session_token
    r = _client().get(path, headers={"Authorization": f"Bearer {create_session_token()}"})
    assert r.status_code == 200


def test_health_fails_closed_when_tao_password_unset(monkeypatch):
    monkeypatch.delenv("TAO_PASSWORD", raising=False)
    r = _client().get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_full_watchdog_authenticates(monkeypatch):
    """The in-process /api/health/full poller must not go silent behind the gate."""
    import logging
    import urllib.request as _ureq

    import app.server.cron_watchdogs as cw
    from app.server.auth import verify_session_token

    seen: list[str] = []

    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        seen.append(req.get_header("Authorization") or "")
        raise OSError("stop after capture")

    monkeypatch.setattr(_ureq, "urlopen", fake_urlopen)
    await cw._watchdog_health_full(logging.getLogger("t"))
    assert seen and seen[0].startswith("Bearer ")
    assert verify_session_token(seen[0][7:])
