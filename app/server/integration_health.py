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
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.integration_health")

_LOG_FILE = (
    Path(os.path.dirname(__file__)).parents[1] / ".harness" / "integration-health.jsonl"
)
_AUTH_SCHEME = "Bearer"
_SLACK_SAFE_ERRORS = frozenset({
    "account_inactive",
    "channel_not_found",
    "invalid_auth",
    "is_archived",
    "missing_scope",
    "no_permission",
    "not_in_channel",
    "ratelimited",
    "restricted_action",
    "team_access_not_granted",
    "token_revoked",
})
_SLACK_USER_ID_RE = re.compile(r"^[UW][A-Z0-9]{8,31}$")

# In-memory state exposed by autonomy_status() / integrations_health()
_last_snapshot: dict[str, Any] = {}
_last_tick_at: float = 0.0
_tick_count: int = 0
# State transitions (healthy → unhealthy) trigger Telegram; repeats don't spam.
_last_state: dict[str, bool] = {}


class _NoSlackRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so Slack credentials never cross an origin boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_SLACK_OPENER = urllib.request.build_opener(_NoSlackRedirect())


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
        headers={
            "Authorization": _AUTH_SCHEME + " " + token,
            "Accept": "application/vnd.github+json",
        },
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


def _safe_slack_error(value: Any) -> str:
    """Return only allowlisted Slack error codes; provider text never escapes."""
    candidate = str(value or "").strip()
    return candidate if candidate in _SLACK_SAFE_ERRORS else "slack_error"


def _safe_slack_user_id(value: Any) -> str:
    """Return a syntactically valid Slack user ID or an empty string."""
    candidate = str(value or "").strip()
    return candidate if _SLACK_USER_ID_RE.fullmatch(candidate) else ""


def _slack_api_json(
    token: str, method: str, payload: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call Slack without redirects and retain only fixed status fields."""
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload or {}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": _AUTH_SCHEME + " " + token,
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with _SLACK_OPENER.open(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        error = "redirect_rejected" if 300 <= exc.code < 400 else "http_error"
        return {"ok": False, "error": error, "user_id": ""}
    except Exception:
        return {"ok": False, "error": "network_error", "user_id": ""}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_response", "user_id": ""}
    return {
        "ok": bool(data.get("ok")),
        "error": "" if data.get("ok") else _safe_slack_error(data.get("error")),
        # Slack bot user IDs are identifiers, not credentials. Keeping only
        # this validated field lets an operator invite an authenticated bot
        # into a private channel without exposing a token or provider payload.
        "user_id": _safe_slack_user_id(data.get("user_id")),
    }


def _presence(value: str) -> str:
    """Render config presence without exposing its value."""
    return "present" if value else "missing"


def _probe_slack_bridge() -> tuple[bool, str]:
    """Verify bridge config, bot identity, and private-channel accessibility."""
    enabled_raw = (os.environ.get("SLACK_TELEGRAM_BRIDGE_ENABLED") or "0").strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"}
    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    signing = (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()
    channel = (os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL") or "").strip()
    state = (
        f"enabled={1 if enabled else 0};"
        f"token={_presence(token)};"
        f"signing={_presence(signing)};"
        f"channel={_presence(channel)}"
    )
    if not enabled:
        return False, f"bridge_disabled;{state}"
    if not token:
        return False, f"bot_token_missing;{state}"
    if not signing:
        return False, f"signing_secret_missing;{state}"
    if not channel:
        return False, f"strengthening_channel_missing;{state}"

    auth = _slack_api_json(token, "auth.test")
    bot_user = auth.get("user_id") or "unknown"
    if not auth.get("ok"):
        return False, f"bot_auth_failed:{auth.get('error') or 'slack_error'};{state}"
    channel_result = _slack_api_json(token, "conversations.info", {"channel": channel})
    if not channel_result.get("ok"):
        return (
            False,
            f"channel_inaccessible:{channel_result.get('error') or 'slack_error'};"
            f"bot_user={bot_user};{state}",
        )
    return True, f"ready;bot_user={bot_user};{state}"


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

    # Small startup delay so the other daemons are up first.
    await asyncio.sleep(15)

    while True:
        try:
            # All probe implementations use blocking stdlib HTTP. Keep the
            # complete health pass off FastAPI's event loop so a slow provider
            # cannot stall unrelated requests while health is being measured.
            await asyncio.to_thread(tick)
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
