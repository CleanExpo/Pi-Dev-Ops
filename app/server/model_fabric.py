"""Mission Control Model Fabric adapter.

OmniRoute is infrastructure behind Mission Control, never the authority layer.
This module provides a narrow OpenAI-compatible seam for approved Pi-CEO roles
and a small telemetry snapshot for the `/control/model` surface.

Founder traffic invariants:
- Ollama and Gemma are blocked.
- OmniRoute is opt-in with OMNIROUTE_ENABLED=1.
- Only roles listed in OMNIROUTE_ROLES are routed through the fabric.
- A fabric failure returns an error so provider_router can use its existing
  high-trust fallback path; it never silently falls back to a banned model.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("app.server.model_fabric")

DEFAULT_BASE_URL = "http://127.0.0.1:20128"
DEFAULT_ROLES = "margot.casual"
DEFAULT_LANE_MODELS = {
    "founder-chat": "auto",
    "internal-work": "auto",
    "research": "auto/smart",
    "coding": "auto/coding",
    "background": "auto/cheap",
}
BANNED_MODEL_MARKERS = ("gemma", "ollama")


@dataclass
class FabricCall:
    ts: float
    role: str
    lane: str
    requested_model: str
    served_model: str
    provider: str
    latency_ms: int
    ok: bool
    error: str | None = None


_lock = threading.Lock()
_last_call: FabricCall | None = None
_total_calls = 0
_total_failures = 0


def enabled() -> bool:
    return (os.environ.get("OMNIROUTE_ENABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def base_url() -> str:
    return (os.environ.get("OMNIROUTE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def allowed_roles() -> set[str]:
    raw = (os.environ.get("OMNIROUTE_ROLES") or DEFAULT_ROLES).strip()
    return {item.strip() for item in raw.split(",") if item.strip()}


def role_allowed(role: str) -> bool:
    return enabled() and role in allowed_roles()


def lane_for_role(role: str) -> str:
    if role == "margot.casual":
        return "founder-chat"
    if role.startswith("research") or role == "realtime_lookup":
        return "research"
    if "code" in role or role in {"generator", "evaluator"}:
        return "coding"
    if role in {"monitor", "guardian", "scribe.draft", "suggestion"}:
        return "background"
    return "internal-work"


def model_for_lane(lane: str) -> str:
    env_key = "OMNIROUTE_MODEL_" + lane.replace("-", "_").upper()
    return (os.environ.get(env_key) or DEFAULT_LANE_MODELS.get(lane) or "auto").strip()


def _is_banned_model(model: str) -> bool:
    lowered = (model or "").lower()
    return any(marker in lowered for marker in BANNED_MODEL_MARKERS)


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = (os.environ.get("OMNIROUTE_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _remember(call: FabricCall) -> None:
    global _last_call, _total_calls, _total_failures
    with _lock:
        _last_call = call
        _total_calls += 1
        if not call.ok:
            _total_failures += 1


def complete(
    *,
    prompt: str,
    role: str,
    session_id: str = "",
    timeout_s: float = 120.0,
    max_tokens: int = 4096,
) -> tuple[int, str, float, str | None]:
    """Run one approved inference through OmniRoute.

    Returns the provider-router tuple `(rc, text, cost_usd, error)`. OmniRoute
    cost is intentionally reported as 0 here; Pi-CEO records routing telemetry
    while OmniRoute remains the source for provider-level quota/cost analytics.
    """
    if not role_allowed(role):
        return 1, "", 0.0, "omniroute_role_not_enabled"

    lane = lane_for_role(role)
    requested_model = model_for_lane(lane)
    if _is_banned_model(requested_model):
        return 1, "", 0.0, f"omniroute_banned_model:{requested_model}"

    payload = {
        "model": requested_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.25,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = _headers()
    if session_id:
        headers["X-Session-Id"] = session_id
    req = urllib.request.Request(
        f"{base_url()}/v1/chat/completions",
        data=data,
        headers=headers,
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            raw = json.loads(response.read().decode("utf-8"))
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        latency_ms = int((time.monotonic() - t0) * 1000)
        error = f"omniroute_http_{exc.code}:{body}"
        _remember(FabricCall(time.time(), role, lane, requested_model, "", "", latency_ms, False, error))
        return 1, "", 0.0, error
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - t0) * 1000)
        error = f"omniroute_call_raised:{exc}"
        _remember(FabricCall(time.time(), role, lane, requested_model, "", "", latency_ms, False, error))
        return 1, "", 0.0, error

    latency_ms = int((time.monotonic() - t0) * 1000)
    choices = raw.get("choices") or []
    text = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            text = str(message.get("content") or "").strip()
    served_model = str(raw.get("model") or requested_model)
    provider = (
        response_headers.get("x-omniroute-provider")
        or response_headers.get("x-provider")
        or str(raw.get("provider") or "")
    )
    if _is_banned_model(served_model) or _is_banned_model(provider):
        error = f"omniroute_served_banned_route:{provider}:{served_model}"
        _remember(FabricCall(time.time(), role, lane, requested_model, served_model, provider, latency_ms, False, error))
        return 1, "", 0.0, error
    if not text:
        error = "omniroute_empty_response"
        _remember(FabricCall(time.time(), role, lane, requested_model, served_model, provider, latency_ms, False, error))
        return 1, "", 0.0, error

    _remember(FabricCall(time.time(), role, lane, requested_model, served_model, provider, latency_ms, True, None))
    log.info(
        "model_fabric role=%s lane=%s model=%s served=%s provider=%s latency_ms=%d",
        role, lane, requested_model, served_model, provider or "unknown", latency_ms,
    )
    return 0, text, 0.0, None


def _get_json(path: str, timeout_s: float = 3.0) -> tuple[bool, Any]:
    req = urllib.request.Request(f"{base_url()}{path}", headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def status_snapshot() -> dict[str, Any]:
    """Return the bounded Mission Control telemetry contract."""
    ping_ok, ping = _get_json("/api/health/ping") if enabled() else (False, "disabled")
    models_ok, models = _get_json("/v1/models") if ping_ok else (False, None)
    with _lock:
        last = asdict(_last_call) if _last_call else None
        totals = {"calls": _total_calls, "failures": _total_failures}

    model_count = 0
    if models_ok and isinstance(models, dict):
        data = models.get("data")
        if isinstance(data, list):
            model_count = len(data)

    return {
        "enabled": enabled(),
        "healthy": bool(ping_ok),
        "base_url": base_url(),
        "allowed_roles": sorted(allowed_roles()),
        "lanes": {
            lane: {"model": model_for_lane(lane), "banned": _is_banned_model(model_for_lane(lane))}
            for lane in DEFAULT_LANE_MODELS
        },
        "models_available": model_count,
        "last_call": last,
        "totals": totals,
        "ping": ping if ping_ok else None,
        "error": None if ping_ok else str(ping),
        "blocked": ["ollama", "gemma"],
    }


__all__ = [
    "allowed_roles",
    "base_url",
    "complete",
    "enabled",
    "lane_for_role",
    "model_for_lane",
    "role_allowed",
    "status_snapshot",
]
