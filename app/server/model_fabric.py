"""Mission Control Model Fabric adapter.

OmniRoute is infrastructure behind Mission Control, never the authority layer.
This module supplies an explicit, allowlisted model ladder for selected roles,
model-level failover, a Margot strengthening pass, and bounded telemetry for the
native `/control/model` surface.

Founder traffic invariants:
- Ollama and Gemma are blocked.
- Global OmniRoute `auto` is not used for founder traffic by default.
- Only roles listed in OMNIROUTE_ROLES are routed through the fabric.
- A fabric failure returns an error so the existing direct high-trust provider
  path can take over; it never silently falls back to a banned model.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("app.server.model_fabric")

DEFAULT_BASE_URL = "http://127.0.0.1:20128"
DEFAULT_ROLES = "margot.casual"

DEFAULT_LANE_MODELS: dict[str, tuple[str, ...]] = {
    "founder-chat": (
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/z-ai/glm-4.7-flash",
        "openrouter/anthropic/claude-sonnet-latest",
    ),
    "internal-work": (
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/z-ai/glm-4.7-flash",
    ),
    "research": (
        "openrouter/perplexity/sonar-pro",
        "openrouter/anthropic/claude-sonnet-latest",
    ),
    "coding": (
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/anthropic/claude-sonnet-latest",
    ),
    "background": (
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/z-ai/glm-4.7-flash",
    ),
}
DEFAULT_STRENGTH_MODEL = "openrouter/anthropic/claude-sonnet-latest"
BANNED_MODEL_MARKERS = ("gemma", "ollama")

_STRENGTH_SIGNALS = re.compile(
    r"\b(?:finish|finalise|finalize|production|strategy|build|fix|repair|"
    r"research|mission control|model|slack|telegram|issue|problem|deploy|"
    r"security|legal|money|revenue|customer|critical|urgent|architecture)\b",
    re.I,
)


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
    attempts: list[str]
    strengthened: bool = False
    error: str | None = None


_lock = threading.Lock()
_last_call: FabricCall | None = None
_total_calls = 0
_total_failures = 0
_total_fallbacks = 0
_total_strengthened = 0


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


def models_for_lane(lane: str) -> list[str]:
    env_key = "OMNIROUTE_MODELS_" + lane.replace("-", "_").upper()
    raw = (os.environ.get(env_key) or "").strip()
    models = [item.strip() for item in raw.split(",") if item.strip()] if raw else list(DEFAULT_LANE_MODELS.get(lane, ()))
    return [model for model in models if not _is_banned_model(model)]


def strength_model() -> str:
    value = (os.environ.get("OMNIROUTE_MODEL_STRENGTHEN") or DEFAULT_STRENGTH_MODEL).strip()
    return "" if _is_banned_model(value) else value


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
    global _last_call, _total_calls, _total_failures, _total_fallbacks, _total_strengthened
    with _lock:
        _last_call = call
        _total_calls += 1
        if not call.ok:
            _total_failures += 1
        if len(call.attempts) > 1:
            _total_fallbacks += 1
        if call.strengthened:
            _total_strengthened += 1


def _chat_once(
    *,
    prompt: str,
    model: str,
    session_id: str,
    timeout_s: float,
    max_tokens: int,
) -> tuple[bool, str, str, str, int, str | None]:
    if not model or _is_banned_model(model):
        return False, "", "", "", 0, f"omniroute_banned_model:{model}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.25,
        "stream": False,
    }
    headers = _headers()
    if session_id:
        headers["X-Session-Id"] = session_id
    req = urllib.request.Request(
        f"{base_url()}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            raw = json.loads(response.read().decode("utf-8"))
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        return False, "", "", "", int((time.monotonic() - t0) * 1000), f"omniroute_http_{exc.code}:{body}"
    except Exception as exc:  # noqa: BLE001
        return False, "", "", "", int((time.monotonic() - t0) * 1000), f"omniroute_call_raised:{exc}"

    latency_ms = int((time.monotonic() - t0) * 1000)
    choices = raw.get("choices") or []
    text = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            text = str(message.get("content") or "").strip()
    served_model = str(raw.get("model") or model)
    provider = (
        response_headers.get("x-omniroute-provider")
        or response_headers.get("x-provider")
        or str(raw.get("provider") or "")
    )
    if _is_banned_model(served_model) or _is_banned_model(provider):
        return False, "", served_model, provider, latency_ms, f"omniroute_served_banned_route:{provider}:{served_model}"
    if not text:
        return False, "", served_model, provider, latency_ms, "omniroute_empty_response"
    return True, text, served_model, provider, latency_ms, None


def _should_strengthen(role: str, prompt: str) -> bool:
    if role != "margot.casual":
        return False
    mode = (os.environ.get("OMNIROUTE_STRENGTHEN_MARGOT") or "smart").strip().lower()
    if mode in {"0", "off", "false", "no"}:
        return False
    if mode in {"1", "on", "true", "always"}:
        return True
    return len(prompt) >= 600 or bool(_STRENGTH_SIGNALS.search(prompt))


def _strength_prompt(original_prompt: str, draft: str) -> str:
    return (
        "You are the senior strengthening pass for Phill McGurk's Mission Control. "
        "Review the draft below against the original prompt. Correct lost context, "
        "unsupported claims, shallow reasoning, uncompleted actions, and drift from "
        "the operator's actual goal. Preserve useful detail but return ONE final, "
        "direct answer suitable for Margot to send. Do not discuss this review step.\n\n"
        f"ORIGINAL PROMPT:\n{original_prompt}\n\n"
        f"DRAFT:\n{draft}\n\n"
        "FINAL STRENGTHENED ANSWER:"
    )


def _post_slack_trace(call: FabricCall) -> None:
    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    channel = (
        os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL")
        or "C0BTX0LRZQ8"
    ).strip()
    if not token or not channel:
        return
    text = (
        "*Margot Model Fabric*\n"
        f"lane: `{call.lane}` · served: `{call.served_model or 'unknown'}` · "
        f"provider: `{call.provider or 'unknown'}` · {call.latency_ms}ms\n"
        f"attempts: {', '.join(f'`{x}`' for x in call.attempts)}\n"
        f"strengthened: {'yes' if call.strengthened else 'no'} · result: {'PASS' if call.ok else 'FAIL'}"
    )
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as exc:  # noqa: BLE001
        log.debug("model_fabric Slack trace suppressed: %s", exc)


def complete(
    *,
    prompt: str,
    role: str,
    session_id: str = "",
    timeout_s: float = 120.0,
    max_tokens: int = 4096,
) -> tuple[int, str, float, str | None]:
    if not role_allowed(role):
        return 1, "", 0.0, "omniroute_role_not_enabled"

    lane = lane_for_role(role)
    models = models_for_lane(lane)
    if not models:
        return 1, "", 0.0, f"omniroute_no_approved_models:{lane}"

    attempts: list[str] = []
    total_latency = 0
    last_error: str | None = None
    draft = ""
    served_model = ""
    provider = ""

    for model in models:
        attempts.append(model)
        ok, text, served, prov, latency_ms, error = _chat_once(
            prompt=prompt,
            model=model,
            session_id=session_id,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
        )
        total_latency += latency_ms
        if ok:
            draft, served_model, provider = text, served, prov
            break
        last_error = error

    if not draft:
        call = FabricCall(time.time(), role, lane, attempts[0], served_model, provider, total_latency, False, attempts, False, last_error)
        _remember(call)
        _post_slack_trace(call)
        return 1, "", 0.0, last_error or "omniroute_ladder_exhausted"

    strengthened = False
    if _should_strengthen(role, prompt):
        reviewer = strength_model()
        if reviewer and reviewer != served_model:
            attempts.append(reviewer)
            ok, text, served, prov, latency_ms, error = _chat_once(
                prompt=_strength_prompt(prompt, draft),
                model=reviewer,
                session_id=f"{session_id}-strength" if session_id else "margot-strength",
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )
            total_latency += latency_ms
            if ok and text:
                draft, served_model, provider = text, served, prov
                strengthened = True
            else:
                last_error = error

    call = FabricCall(time.time(), role, lane, models[0], served_model, provider, total_latency, True, attempts, strengthened, None)
    _remember(call)
    _post_slack_trace(call)
    log.info(
        "model_fabric role=%s lane=%s served=%s provider=%s attempts=%d strengthened=%s latency_ms=%d",
        role, lane, served_model, provider or "unknown", len(attempts), strengthened, total_latency,
    )
    return 0, draft, 0.0, None


def _get_json(path: str, timeout_s: float = 3.0) -> tuple[bool, Any]:
    req = urllib.request.Request(f"{base_url()}{path}", headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def status_snapshot() -> dict[str, Any]:
    ping_ok, ping = _get_json("/api/health/ping") if enabled() else (False, "disabled")
    models_ok, models = _get_json("/v1/models") if ping_ok else (False, None)
    with _lock:
        last = asdict(_last_call) if _last_call else None
        totals = {
            "calls": _total_calls,
            "failures": _total_failures,
            "fallbacks": _total_fallbacks,
            "strengthened": _total_strengthened,
        }

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
            lane: {
                "models": models_for_lane(lane),
                "model": " → ".join(models_for_lane(lane)),
                "banned": any(_is_banned_model(model) for model in models_for_lane(lane)),
            }
            for lane in DEFAULT_LANE_MODELS
        },
        "strength_model": strength_model(),
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
    "models_for_lane",
    "role_allowed",
    "status_snapshot",
    "strength_model",
]
