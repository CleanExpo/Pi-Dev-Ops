"""Shared helpers for phone-companion hooks (RA-1457 S-slice).

Kept dependency-free — stdlib only. Imported by every script under
~/.claude/hooks/phone/.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LOG_DIR = Path(os.path.expanduser("~/.claude/hooks/phone"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG = LOG_DIR / "last_error.log"
STATE_FILE = LOG_DIR / "state.json"
THROTTLE_FILE = LOG_DIR / "progress_throttle.json"

DEFAULT_BACKEND = "https://pi-dev-ops-production.up.railway.app"
TIMEOUT_S = 60.0
POLL_INTERVAL = 2.0
PROGRESS_THROTTLE_S = 10.0


def log_error(msg: str) -> None:
    try:
        with ERROR_LOG.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def backend_base() -> str:
    return os.environ.get("PICEO_BACKEND_URL", DEFAULT_BACKEND).rstrip("/")


def backend_password() -> str:
    pw = os.environ.get("TAO_PASSWORD", "").strip()
    if pw:
        return pw
    # Secondary: read from ~/.claude/hooks/phone/.env
    envf = LOG_DIR / ".env"
    if envf.is_file():
        for line in envf.read_text().splitlines():
            if line.startswith("TAO_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, STATE_FILE)
    except Exception as exc:
        log_error(f"save_state failed: {exc}")


def get_token() -> str | None:
    """Return a valid backend bearer token — login if cache missing/expired."""
    state = _load_state()
    tok = state.get("token")
    exp = state.get("token_exp", 0)
    if tok and exp > time.time() + 60:
        return tok

    pw = backend_password()
    if not pw:
        log_error("TAO_PASSWORD not available — cannot auth to backend")
        return None

    try:
        req = urllib.request.Request(
            f"{backend_base()}/api/login",
            data=json.dumps({"password": pw}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Try Set-Cookie first (works even when JSON body doesn't include token)
            token = None
            for c in resp.headers.get_all("Set-Cookie") or []:
                if c.startswith("tao_session="):
                    token = c.split(";", 1)[0].split("=", 1)[1]
                    break
            if not token:
                body = json.loads(resp.read() or b"{}")
                token = body.get("token")
    except Exception as exc:
        log_error(f"login failed: {exc}")
        return None

    if not token:
        log_error("login returned no token")
        return None

    state["token"] = token
    # SESSION_TTL defaults to 2 h on the backend — cache for 30 min to be safe
    state["token_exp"] = time.time() + 1800
    _save_state(state)
    return token


def backend_post(path: str, body: dict, timeout: float = 10.0) -> tuple[int, dict]:
    tok = get_token()
    if not tok:
        return 0, {"error": "no token"}
    req = urllib.request.Request(
        f"{backend_base()}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tok}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="ignore") if exc.fp else ""
        log_error(f"POST {path} HTTP {exc.code}: {detail}")
        return exc.code, {"error": detail}
    except Exception as exc:
        log_error(f"POST {path} transport: {exc}")
        return 0, {"error": str(exc)}


def backend_get(path: str, timeout: float = 10.0) -> tuple[int, dict]:
    tok = get_token()
    if not tok:
        return 0, {"error": "no token"}
    req = urllib.request.Request(
        f"{backend_base()}{path}",
        headers={"Authorization": f"Bearer {tok}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="ignore") if exc.fp else ""
        log_error(f"GET {path} HTTP {exc.code}: {detail}")
        return exc.code, {"error": detail}
    except Exception as exc:
        log_error(f"GET {path} transport: {exc}")
        return 0, {"error": str(exc)}


def read_hook_payload() -> dict:
    """Claude Code hooks receive the tool-call JSON on stdin."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:500]}


def session_id_from_payload(payload: dict) -> str:
    return (
        payload.get("session_id")
        or payload.get("sessionId")
        or os.environ.get("CLAUDE_SESSION_ID")
        or "unknown"
    )
