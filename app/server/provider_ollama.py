"""Explicit local Ollama transport with per-call served-model evidence.

Only loopback endpoints pass the subscription-only policy. The legacy tuple
API remains available; the rich result retains model metadata from the actual
response. Selection never silently falls back to a paid provider.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, TYPE_CHECKING

from . import provider_policy

if TYPE_CHECKING:
    from .provider_execution_types import ProviderExecution

log = logging.getLogger("app.server.provider_ollama")

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TAGS_URL = "http://localhost:11434/api/tags"
HTTP_TIMEOUT_S_DEFAULT = 120.0
PROBE_TIMEOUT_S = 1.0
PROBE_CACHE_TTL_S = 60.0

# Module-level reachability cache: (was_reachable, checked_at_unix_seconds)
_REACHABLE_CACHE: dict[str, tuple[bool, float]] = {}


def _base_url(override: str | None = None) -> str:
    """OLLAMA_BASE_URL (or the default) unless the caller supplies its own.

    ``override`` exists for provider_router's margot.casual ladder (RA-7434),
    which reads MARGOT_OLLAMA_BASE_URL so the Railway start guard can keep
    stripping the global key from every work lane.
    """
    return (override or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _tags_url(base_url: str | None = None) -> str:
    base = _base_url(base_url)
    if base.endswith("/v1"):
        return base[:-3] + "/api/tags"
    return f"{base}/api/tags"


# ── Reachability probe ──────────────────────────────────────────────────────


def is_reachable(*, force_refresh: bool = False, base_url: str | None = None) -> bool:
    """True when localhost:11434 (or override) responds within PROBE_TIMEOUT_S.

    Cached for PROBE_CACHE_TTL_S to avoid hammering Ollama on every
    cycle. force_refresh=True bypasses the cache (use sparingly).
    base_url probes a specific Ollama instead of OLLAMA_BASE_URL.
    """
    url = _tags_url(base_url)
    try:
        provider_policy.require_transport("ollama", endpoint_url=url)
    except provider_policy.ProviderPolicyError:
        return False
    now = time.time()

    if not force_refresh:
        cached = _REACHABLE_CACHE.get(url)
        if cached is not None:
            reachable, checked_at = cached
            if (now - checked_at) < PROBE_CACHE_TTL_S:
                return reachable

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.debug("ollama: httpx unavailable for probe (%s)", exc)
        _REACHABLE_CACHE[url] = (False, now)
        return False

    try:
        with httpx.Client(timeout=PROBE_TIMEOUT_S) as client:
            r = client.get(url)
            ok = r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        log.debug("ollama: probe %s failed (%s)", url, exc)
        ok = False

    _REACHABLE_CACHE[url] = (ok, now)
    return ok


def clear_reachability_cache() -> None:
    """For tests + manual override."""
    _REACHABLE_CACHE.clear()


# ── Headers / body ──────────────────────────────────────────────────────────


def _build_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer ollama",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _build_body(prompt: str, model_id: str, *, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model_id,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }


def _extract_text(response: dict[str, Any]) -> str:
    """OpenAI Chat Completions shape — same as OpenRouter."""
    choices = response.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


# ── Public entry ────────────────────────────────────────────────────────────


async def call_with_evidence(*, prompt: str, model_id: str,
                 timeout_s: float = HTTP_TIMEOUT_S_DEFAULT,
                 max_tokens: int = 4096,
                 role: str = "",
                 session_id: str = "", base_url: str | None = None,
                 ) -> ProviderExecution:
    """One local call with served-model metadata kept on its own result."""
    from .provider_execution_types import ProviderExecution

    evidence = {"provider": "ollama", "transport": "ollama", "requested_model": model_id,
                "actual_model": None, "model_verified": False, "auth_verified": False,
                "billing_class": "unknown", "source": "provider_ollama"}
    headers = _build_headers()
    body = _build_body(prompt, model_id, max_tokens=max_tokens)

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return ProviderExecution(1, "", 0.0, f"ollama_httpx_import_failed: {exc}", evidence)

    def _do_call() -> ProviderExecution:
        url = f"{_base_url(base_url)}/chat/completions"
        try:
            evidence.update(provider_policy.require_transport("ollama", endpoint_url=url))
        except provider_policy.ProviderPolicyError as exc:
            return ProviderExecution(1, "", 0.0, str(exc), evidence)
        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(url, headers=headers, json=body)
        except Exception as exc:  # noqa: BLE001
            return ProviderExecution(1, "", 0.0, f"ollama_call_raised: {exc}", evidence)
        return _decode_response(r, evidence, role, model_id)

    return await asyncio.to_thread(_do_call)


async def call(*, prompt: str, model_id: str, timeout_s: float = HTTP_TIMEOUT_S_DEFAULT,
               max_tokens: int = 4096, role: str = "", session_id: str = "", base_url: str | None = None,
               ) -> tuple[int, str, float | None, str | None]:
    """Legacy tuple interface; richer callers retain per-call response evidence."""
    outcome = await call_with_evidence(prompt=prompt, model_id=model_id, timeout_s=timeout_s,
                                       max_tokens=max_tokens, role=role, session_id=session_id, base_url=base_url)
    return outcome.as_tuple()


__all__ = ["call", "call_with_evidence", "is_reachable", "clear_reachability_cache"]


def _decode_response(response, evidence, role, model_id):
    from .provider_execution_types import ProviderExecution
    if response.status_code >= 400:
        body_snippet = (response.text or "")[:500]
        return ProviderExecution(1, "", 0.0,
            f"ollama_http_{response.status_code}: {body_snippet}", evidence)
    try:
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        return ProviderExecution(1, "", 0.0, f"ollama_bad_json: {exc}", evidence)
    if not isinstance(data, dict):
        return ProviderExecution(1, "", 0.0, "ollama_invalid_response", evidence)
    reported = data.get("model")
    if isinstance(reported, str) and reported.strip():
        evidence.update(actual_model=reported.strip(), model_verified=True,
                        model_source="ollama_response.model")
    text = _extract_text(data)
    if not text:
        return ProviderExecution(1, "", 0.0, "ollama_empty_response", evidence)
    log.info(
        "ollama %s: %d chars, $0 (model=%s, local)",
        role or "?", len(text), model_id,
    )
    return ProviderExecution(0, text, 0.0, None, evidence)
