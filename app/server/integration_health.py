"""
integration_health.py — RA-1293.

Probes every external dependency Pi-CEO needs to do its job, every 60 s.
When a dependency flips from healthy to unhealthy, pings the founder via
Telegram so broken auth is noticed BEFORE it silently kills autonomous work.

Dependencies probed (in priority order):

    linear_api_key   — Linear GraphQL `viewer` query. Auth errors are the
                       silent-killer pattern RA-1154 warned about; RA-1289's
                       cross-project poller is useless without this key valid.
    github_token     — GitHub REST `/user`. Required for push + PR open
                       (RA-1183).
    slack_bridge     — Margot Slack bridge enablement, secret presence, bot
                       auth, and access to the private strengthening channel.
    linear_poll_live — autonomy._last_poll_at within 2× poll interval.

Kill switch: TAO_INTEGRATION_HEALTH_ENABLED=0 in Railway env.

Observability:
    /api/integrations/health    — public JSON snapshot
    .harness/integration-health.jsonl — append log (every tick)

Recovery hooks:
    None are attempted here — rotating secrets needs a human. The system's
    job is to detect and notify loudly, so the human can act. That IS the
    fix for the "silent drop" class of bug (RA-1109 surface-treatment
    prohibition applied to ops health).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.integration_health")

_LOG_FILE = (
    Path(os.path.dirname(__file__)).parents[1] / ".harness" / "integration-health.jsonl"
)

# In-memory state exposed by autonomy_status() / integrations_health()
_last_snapshot: dict[str, Any] = {}
_last_tick_at: float = 0.0
_tick_count: int = 0
# State transitions (healthy → unhealthy) trigger Telegram; repeats don't spam.
_last_state: dict[str, bool] = {}


# -----------------------------------------------------------------------------
# Probe helpers
# -----------------------------------------------------------------------------

def _probe_linear_api_key() -> tuple[bool, str]:
    """Cheap `viewer` query — valid key returns 200, expired returns 401."""
    key = os.environ.get("LINEAR_API_KEY", "")
    if not key:
        return False, "LINEAR_API_KEY env var not set"
    payload = json.dumps({"query": "query { viewer { id } }"}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"network: {exc}"
    if "errors" in data:
        return False, f"gql: {data['errors'][0].get('message', 'unknown')[:80]}"
    return True, "ok"


def _probe_github_token() -> tuple[bool, str]:
    """GitHub /user — valid token returns 200 with login field."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN env var not set"
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"network: {exc}"
    login = data.get("login")
    return (bool(login), f"login={login}" if login else "no login in response")


def _slack_api_probe(
    token: str, method: str, payload: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Call Slack with a token but return only ok/error state, never response data."""
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload or {}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception:
        return False, "network_or_invalid_response"
    if not isinstance(data, dict):
        return False, "invalid_response"
    if data.get("ok"):
        return True, "ok"
    error = str(data.get("error") or "unknown")[:80]
    return False, error


def _probe_slack_bridge() -> tuple[bool, str]:
    """Verify bridge config, Slack bot validity, and private-channel accessibility."""
    enabled = (os.environ.get("SLACK_TELEGRAM_BRIDGE_ENABLED") or "0").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return False, "bridge_disabled"

    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    signing = (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
    channel = (os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL") or "").strip()
    if not token:
        return False, "bot_token_missing"
    if not signing:
        return False, "signing_secret_missing"
    if not channel:
        return False, "strengthening_channel_missing"

    auth_ok, auth_detail = _slack_api_probe(token, "auth.test")
    if not auth_ok:
        return False, f"bot_auth_failed:{auth_detail}"
    channel_ok, channel_detail = _slack_api_probe(
        token, "conversations.info", {"channel": channel},
    )
    if not channel_ok:
        return False, f"channel_inaccessible:{channel_detail}"
    return True, "ready"


def _probe_linear_poll_live() -> tuple[bool, str]:
    """autonomy._last_poll_at must be within 2× the poll interval — otherwise
    the poller is silently wedged even if the key works."""
    from . import autonomy  # late import to avoid startup circular
    interval = int(os.environ.get("TAO_AUTONOMY_POLL_INTERVAL", "300"))
    threshold = interval * 2
    now = time.time()
    last = getattr(autonomy, "_last_poll_at", 0.0)
    if not last:
        return False, "poller has not run yet (startup grace period ok for first 2 min)"
    age = int(now - last)
    return (age <= threshold, f"last_poll_age_s={age} (threshold={threshold})")


_PROBES = {
    "linear_api_key":   _probe_linear_api_key,
    "github_token":     _probe_github_token,
    "slack_bridge":     _probe_slack_bridge,
    "linear_poll_live": _probe_linear_poll_live,
}


# -----------------------------------------------------------------------------
# Telegram escalation
# -----------------------------------------------------------------------------

def _notify_telegram(name: str, detail: str) -> None:
    """Ping Telegram on a healthy → unhealthy transition. Best-effort."""
    try:
        # Late import — scripts/ is on sys.path via app_factory startup hook
        import sys
        scripts_dir = str(Path(__file__).parents[2] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from send_telegram import send_telegram  # type: ignore
        msg = (
            f"⚠️ Pi-CEO integration check FAILED\n\n"
            f"Integration: {name}\n"
            f"Detail: {detail}\n\n"
            f"Fix before autonomous work starts silently no-op'ing. See RA-1293 runbook."
        )
        send_telegram(msg)
        log.warning("integration-health: telegram nudge sent for %s", name)
    except SystemExit as exc:
        # send_telegram is also a CLI helper and raises SystemExit when optional
        # routing is absent. Contain that CLI signal at this best-effort boundary
        # so it cannot terminate the FastAPI lifespan.
        log.warning(
            "integration-health: telegram nudge skipped for %s: config exit %s",
            name,
            exc.code,
        )
    except Exception as exc:
        # Don't let notification failure kill the daemon
        log.warning("integration-health: telegram nudge failed for %s: %s", name, exc)


# -----------------------------------------------------------------------------
# Tick
# -----------------------------------------------------------------------------

def tick() -> dict[str, Any]:
    """Run every probe, record results, fire Telegram on transitions."""
    global _last_snapshot, _last_tick_at, _tick_count
    _tick_count += 1
    _last_tick_at = time.time()

    results: dict[str, Any] = {}
    for name, probe in _PROBES.items():
        try:
            ok, detail = probe()
        except Exception as exc:
            ok, detail = False, f"probe crashed: {exc}"
        results[name] = {"ok": ok, "detail": detail}

        # Transition detection
        prev = _last_state.get(name)
        if prev is True and ok is False:
            _notify_telegram(name, detail)
        _last_state[name] = ok

    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tick": _tick_count,
        "all_healthy": all(r["ok"] for r in results.values()),
        "checks": results,
    }
    _last_snapshot = snapshot

    # Append to log (fire-and-forget)
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot) + "\n")
    except Exception as exc:
        log.warning("integration-health: log write failed: %s", exc)

    return snapshot


# -----------------------------------------------------------------------------
# Daemon + public accessor
# -----------------------------------------------------------------------------

async def integration_health_loop() -> None:
    """Background coroutine. Ticks every TAO_INTEGRATION_HEALTH_INTERVAL (default 60 s)."""
    interval = int(os.environ.get("TAO_INTEGRATION_HEALTH_INTERVAL", "60"))
    enabled = os.environ.get("TAO_INTEGRATION_HEALTH_ENABLED", "1").lower() not in ("0", "false", "no")
    if not enabled:
        log.info("integration-health: disabled via TAO_INTEGRATION_HEALTH_ENABLED=0")
        return
    log.info("integration-health: started (interval=%ds)", interval)

    # Small startup delay so the other daemons are up first
    await asyncio.sleep(15)

    while True:
        try:
            tick()
        except Exception as exc:
            log.error("integration-health: tick crashed: %s", exc)
        await asyncio.sleep(interval)


def get_snapshot() -> dict[str, Any]:
    """Return the last snapshot for /api/integrations/health.

    Shape kept minimal + stable so the dashboard can render it without any
    server-side HTML. `all_healthy` is the single boolean the strip watches.
    """
    return _last_snapshot or {
        "ts": None,
        "tick": 0,
        "all_healthy": None,
        "checks": {name: {"ok": None, "detail": "not yet probed"} for name in _PROBES},
    }
