"""provider_ollama.py — RA-1868 Wave 5.2: local Ollama inference wrapper.

OpenAI-compatible HTTP client for Ollama at localhost:11434/v1. Used as
the preferred cheap-tier path when reachable — free, private, fast.
provider_router auto-falls-back to OpenRouter when Ollama isn't
reachable (e.g. production Railway).

The OpenAI compat path on Ollama matches the OpenRouter wrapper exactly,
so the same code shape works with a different base_url + auth header.

Required env (none — works out of the box on a default Ollama install):
  OLLAMA_BASE_URL    — override default http://localhost:11434/v1

The "API key" Ollama expects is literally the string "ollama" — sent as
a Bearer token but unverified. We send it for OpenAI-spec compliance.

Cost tracking: Ollama returns tokens but no cost (it's free). We surface
cost_usd=0.0 deterministically.

Failure modes:
  Network error / unreachable → (1, "", 0.0, "ollama_call_raised: ...")
  HTTP error                  → (1, "", 0.0, "ollama_http_<status>: ...")
  Empty response              → (1, "", 0.0, "ollama_empty_response")

httpx imported lazily so the module loads in environments without it.

Reachability probe: ``is_reachable()`` does a 1-second HEAD/GET on the
``/api/tags`` endpoint. Used by provider_router to decide cheap-tier
routing on each call (cached for 60s — we don't want to spam Ollama on
every cycle).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

log = logging.getLogger("app.server.provider_ollama")

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TAGS_URL = "http://localhost:11434/api/tags"
HTTP_TIMEOUT_S_DEFAULT = 120.0
PROBE_TIMEOUT_S = 1.0
PROBE_CACHE_TTL_S = 60.0

# Module-level reachability cache: (was_reachable, checked_at_unix_seconds)
_REACHABLE_CACHE: dict[str, tuple[bool, float]] = {}


def _base_url() -> str:
    return (os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _tags_url() -> str:
    base = _base_url()
    if base.endswith("/v1"):
        return base[:-3] + "/api/tags"
    return f"{base}/api/tags"


# ── Reachability probe ──────────────────────────────────────────────────────


def is_reachable(*, force_refresh: bool = False) -> bool:
    """True when localhost:11434 (or override) responds within PROBE_TIMEOUT_S.

    Cached for PROBE_CACHE_TTL_S to avoid hammering Ollama on every
    cycle. force_refresh=True bypasses the cache (use sparingly).
    """
    url = _tags_url()
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


async def call(*, prompt: str, model_id: str,
                 timeout_s: float = HTTP_TIMEOUT_S_DEFAULT,
                 max_tokens: int = 4096,
                 role: str = "",
                 session_id: str = "",
                 ) -> tuple[int, str, float, str | None]:
    """One Ollama call. Returns (rc, text, cost_usd, error_or_None).

    cost_usd is always 0.0 — Ollama is free.
    """
    headers = _build_headers()
    body = _build_body(prompt, model_id, max_tokens=max_tokens)

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"ollama_httpx_import_failed: {exc}"

    def _do_call() -> tuple[int, str, float, str | None]:
        url = f"{_base_url()}/chat/completions"
        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(url, headers=headers, json=body)
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"ollama_call_raised: {exc}"
        if r.status_code >= 400:
            body_snippet = (r.text or "")[:500]
            return 1, "", 0.0, (
                f"ollama_http_{r.status_code}: {body_snippet}"
            )
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"ollama_bad_json: {exc}"
        text = _extract_text(data)
        if not text:
            return 1, "", 0.0, "ollama_empty_response"
        log.info(
            "ollama %s: %d chars, $0 (model=%s, local)",
            role or "?", len(text), model_id,
        )
        return 0, text, 0.0, None

    return await asyncio.to_thread(_do_call)


__all__ = ["call", "is_reachable", "clear_reachability_cache"]
