"""provider_openrouter.py — RA-1868 Wave 5.2: OpenRouter inference wrapper.

OpenAI-compatible HTTP client for OpenRouter. Mission Control can optionally
place the governed OmniRoute Model Fabric in front of selected roles. When the
fabric is unavailable, this module falls back to the existing direct OpenRouter
path. Banned local/Gemma routes are enforced by the fabric and production guard.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("app.server.provider_openrouter")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
HTTP_TIMEOUT_S_DEFAULT = 120.0


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
        "reasoning": {"enabled": False},
    }


def _extract_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    msg = choice.get("message") or {}
    finish = choice.get("finish_reason")
    content = msg.get("content") or ""
    if content:
        if finish not in (None, "", "stop"):
            log.warning(
                "openrouter: returning %d chars that ended on finish_reason=%r "
                "— the response is incomplete", len(content), finish,
            )
        return content
    if finish != "stop":
        return ""
    return msg.get("reasoning") or ""


def _extract_cost_usd(response: dict[str, Any]) -> float:
    usage = response.get("usage") or {}
    cost = usage.get("cost") or usage.get("total_cost") or 0.0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


async def call(*, prompt: str, model_id: str,
                 timeout_s: float = HTTP_TIMEOUT_S_DEFAULT,
                 max_tokens: int = 4096,
                 role: str = "",
                 session_id: str = "",
                 ) -> tuple[int, str, float, str | None]:
    """One model call with Model Fabric first for explicitly approved roles."""
    try:
        from . import model_fabric  # noqa: PLC0415
        if model_fabric.role_allowed(role):
            result = await asyncio.to_thread(
                model_fabric.complete,
                prompt=prompt,
                role=role,
                session_id=session_id,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )
            if int(result[0]) == 0:
                return result
            log.warning(
                "model_fabric failed for role=%s (%s); using direct OpenRouter fallback",
                role or "?", result[3],
            )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "model_fabric seam failed for role=%s (%s); using direct OpenRouter fallback",
            role or "?", exc,
        )

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
