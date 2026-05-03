"""provider_whisper.py — RA-1886: OpenRouter Whisper STT wrapper.

Speech-to-text via OpenRouter's audio/transcriptions endpoint. Different
from chat completions (provider_openrouter.py) — this one uses
multipart/form-data file upload instead of JSON.

Used by /api/margot/voice route to transcribe Telegram voice notes
before feeding the text into swarm.margot_bot.handle_turn.

Required env:
  OPENROUTER_API_KEY — same key as provider_openrouter (one OpenRouter
                        account, multiple endpoints).

Optional env:
  WHISPER_MODEL          — model id (default: openai/whisper-large-v3-turbo)
  WHISPER_TIMEOUT_S      — request timeout (default: 60)
  OPENROUTER_HTTP_REFERER, OPENROUTER_X_TITLE — same as chat client

Failure modes mirror provider_openrouter.py:
  Missing API key  → (1, "", 0.0, "openrouter_no_api_key")
  Missing file     → (1, "", 0.0, "whisper_audio_not_found: <path>")
  Network error    → (1, "", 0.0, "whisper_call_raised: <details>")
  HTTP error       → (1, "", 0.0, "whisper_http_<status>: <body>")
  Empty response   → (1, "", 0.0, "whisper_empty_response")

httpx imported lazily so the module loads in environments without it.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("app.server.provider_whisper")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_WHISPER_MODEL = "openai/whisper-large-v3-turbo"
HTTP_TIMEOUT_S_DEFAULT = 60.0


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_headers() -> dict[str, str]:
    """Authorization + attribution headers (no Content-Type — httpx sets multipart)."""
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "HTTP-Referer": os.environ.get(
            "OPENROUTER_HTTP_REFERER", "https://github.com/CleanExpo",
        ),
        "X-Title": os.environ.get("OPENROUTER_X_TITLE", "pi-ceo"),
    }


def _resolve_model() -> str:
    return (os.environ.get("WHISPER_MODEL") or DEFAULT_WHISPER_MODEL).strip()


def _resolve_timeout() -> float:
    raw = (os.environ.get("WHISPER_TIMEOUT_S") or "").strip()
    if not raw:
        return HTTP_TIMEOUT_S_DEFAULT
    try:
        return float(raw)
    except ValueError:
        return HTTP_TIMEOUT_S_DEFAULT


def _extract_text(response: dict[str, Any]) -> str:
    """OpenAI-compatible transcription response: {"text": "..."}."""
    return (response.get("text") or "").strip()


def _extract_cost_usd(response: dict[str, Any]) -> float:
    """Best-effort cost surface — OpenRouter occasionally returns usage
    on the response. Whisper's cost is duration-based, not token-based,
    so this often returns 0.0; the OpenRouter dashboard remains the
    source of truth for billing."""
    usage = response.get("usage") or {}
    cost = usage.get("cost") or usage.get("total_cost") or 0.0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


# ── Public entry ────────────────────────────────────────────────────────────


async def transcribe(audio_path: Path | str, *,
                       model: str | None = None,
                       timeout_s: float | None = None,
                       role: str = "margot.voice",
                       session_id: str = "",
                       ) -> tuple[int, str, float, str | None]:
    """One Whisper transcription call.

    Returns (rc, transcript, cost_usd, error_or_None) — same shape as
    provider_openrouter.call() so callers get a consistent contract.

    Async, runs the sync httpx call in a worker thread to avoid blocking
    the event loop.
    """
    p = Path(audio_path)
    if not p.exists() or not p.is_file():
        return 1, "", 0.0, f"whisper_audio_not_found: {p}"

    headers = _build_headers()
    if not headers:
        return 1, "", 0.0, "openrouter_no_api_key"

    model_id = (model or _resolve_model()).strip()
    timeout = timeout_s or _resolve_timeout()

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return 1, "", 0.0, f"whisper_httpx_import_failed: {exc}"

    def _do_call() -> tuple[int, str, float, str | None]:
        url = f"{OPENROUTER_API_BASE}/audio/transcriptions"
        try:
            with p.open("rb") as fh:
                files = {
                    "file": (p.name, fh, "application/octet-stream"),
                }
                data = {"model": model_id}
                with httpx.Client(timeout=timeout) as client:
                    r = client.post(url, headers=headers, files=files, data=data)
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"whisper_call_raised: {exc}"
        if r.status_code >= 400:
            body_snippet = (r.text or "")[:500]
            return 1, "", 0.0, f"whisper_http_{r.status_code}: {body_snippet}"
        try:
            response = r.json()
        except Exception as exc:  # noqa: BLE001
            return 1, "", 0.0, f"whisper_bad_json: {exc}"
        text = _extract_text(response)
        cost = _extract_cost_usd(response)
        if not text:
            return 1, "", cost, "whisper_empty_response"
        log.info(
            "whisper %s: %d chars, $%.6f (model=%s, file=%s)",
            role, len(text), cost, model_id, p.name,
        )
        return 0, text, cost, None

    return await asyncio.to_thread(_do_call)


__all__ = ["transcribe", "DEFAULT_WHISPER_MODEL"]
