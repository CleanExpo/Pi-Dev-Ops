"""provider_openrouter.py — RA-1868 Wave 5.2: OpenRouter inference wrapper.

OpenAI-compatible HTTP client for OpenRouter. Used by the cheap tier of
provider_router. Anthropic stays on its native SDK; OpenRouter goes
through this module.

Why OpenAI-compatible: OpenRouter speaks the OpenAI Chat Completions
API for any underlying model (Gemma, Llama, Mistral, etc.). One client,
many models, configurable per-role via env.

Required env:
  OPENROUTER_API_KEY — get from https://openrouter.ai/

Optional env:
  OPENROUTER_HTTP_REFERER  — your site URL, used for OpenRouter's traffic
                              attribution (default: https://github.com/CleanExpo)
  OPENROUTER_X_TITLE       — your app name (default: pi-ceo)

Cost tracking: OpenRouter returns usage tokens + cost in the response.
We surface cost_usd back to the caller so the existing budget tracker
keeps working.

Failure modes:
  Missing API key  → (1, "", 0.0, "openrouter_no_api_key")
  Network error    → (1, "", 0.0, "openrouter_call_raised: <details>")
  HTTP error       → (1, "", 0.0, "openrouter_http_<status>: <body>")
  Empty response   → (1, "", 0.0, "openrouter_empty_response")

httpx imported lazily so the module loads in environments without it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

log = logging.getLogger("app.server.provider_openrouter")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
HTTP_TIMEOUT_S_DEFAULT = 120.0


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_headers() -> dict[str, str]:
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": os.environ.get(
            "OPENROUTER_HTTP_REFERER", "https://github.com/CleanExpo",
        ),
        "X-Title": os.environ.get("OPENROUTER_X_TITLE", "pi-ceo"),
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
    """Pull the assistant text from the OpenAI-compatible response shape."""
    choices = response.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return msg.get("content") or ""


def _extract_cost_usd(response: dict[str, Any]) -> float:
    """OpenRouter exposes cost on the usage block when available.

    Shape varies by model; we read both ``usage.cost`` (preferred) and
    fall back to estimated cost = 0 if absent. Real cost tracking happens
    via OpenRouter's dashboard regardless — this is a best-effort surface
    for the local budget tracker.
    """
    usage = response.get("usage") or {}
    cost = usage.get("cost") or usage.get("total_cost") or 0.0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


# ── Public entry ────────────────────────────────────────────────────────────


async def call(*, prompt: str, model_id: str,
                 timeout_s: float = HTTP_TIMEOUT_S_DEFAULT,
                 max_tokens: int = 4096,
                 role: str = "",
                 session_id: str = "",
                 ) -> tuple[int, str, float, str | None]:
    """One OpenRouter call. Returns (rc, text, cost_usd, error_or_None).

    Async, runs the sync httpx call in a worker thread to avoid blocking
    the event loop. Caller is expected to be in an async context (the
    existing _call_llm pattern).
    """
    headers = _build_headers()
    if not headers:
        return 1, "", 0.0, "openrouter_no_api_key"

    body = _build_body(prompt, model_id, max_tokens=max_tokens)

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"openrouter_httpx_import_failed: {exc}"

    def _do_call() -> tuple[int, str, float, str | None]:
        url = f"{OPENROUTER_API_BASE}/chat/completions"
        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(url, headers=headers, json=body)
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"openrouter_call_raised: {exc}"
        if r.status_code >= 400:
            # Truncate body to keep the error log readable
            body_snippet = (r.text or "")[:500]
            return 1, "", 0.0, (
                f"openrouter_http_{r.status_code}: {body_snippet}"
            )
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"openrouter_bad_json: {exc}"
        text = _extract_text(data)
        cost = _extract_cost_usd(data)
        if not text:
            return 1, "", cost, "openrouter_empty_response"
        log.info(
            "openrouter %s: %d chars, $%.6f (model=%s)",
            role or "?", len(text), cost, model_id,
        )
        return 0, text, cost, None

    return await asyncio.to_thread(_do_call)


__all__ = ["call"]
