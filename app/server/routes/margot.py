"""Margot bridge routes — RA-1871 (text) + RA-1886 (voice).

Lets external callers (today: Hermes daemon's pi-ceo MCP server) drive a
single Margot turn through the Wave-4/5 ``swarm.margot_bot.handle_turn``
pipeline without owning the Telegram bot token themselves.

RA-1886 adds the voice path: caller passes a Telegram file_id, this
route downloads via the Bot API, transcribes via OpenRouter Whisper,
then runs the same handle_turn pipeline with the transcript.

Why this exists:
  Hermes daemon owns the founder's Telegram bot and routes every inbound
  message through its own Margot persona. That persona has all 31 Pi-CEO
  MCP tools but doesn't get the Wave-4/5 enrichment automatically:
    * Operating context (CFO/CMO/CTO/CS daily snippets)
    * Conversation persistence at .harness/margot/conversations/<chat>.jsonl
    * 2-phase research with [RESEARCH] sentinels
    * Board trigger detection
    * 3-tier provider routing (Anthropic top / OpenRouter cheap / Ollama)

  This route exposes ``handle_turn`` over HTTP so the MCP-side bridge
  can call it on demand. Hermes still owns the Telegram send (we set
  ``_send=False``); this route returns the reply text for Hermes to deliver.

Auth: ``X-Pi-CEO-Secret`` header == ``TAO_WEBHOOK_SECRET``. Same scheme
the morning-intel + Linear webhook routes already use.
"""
from __future__ import annotations

import asyncio
import hmac as _hmac
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("pi-ceo.routes.margot")

router = APIRouter()


class MargotTurnRequest(BaseModel):
    chat_id: str = Field(..., description="Telegram chat_id as string")
    user_text: str = Field(..., min_length=1, max_length=4000)
    message_id: Optional[str] = Field(
        default=None, description="Telegram message_id (optional, for traceability)",
    )


class MargotTurnResponse(BaseModel):
    reply: str
    cost_usd: float
    research_called: bool
    board_session_ids: list[str]
    turn_id: str


def _check_secret(x_pi_ceo_secret: Optional[str]) -> None:
    if not config.WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_WEBHOOK_SECRET not configured on server")
    if not x_pi_ceo_secret:
        raise HTTPException(401, "Missing X-Pi-CEO-Secret header")
    if not _hmac.compare_digest(x_pi_ceo_secret, config.WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid X-Pi-CEO-Secret")


@router.post("/api/margot/turn", response_model=MargotTurnResponse)
async def margot_turn(
    body: MargotTurnRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Drive one Margot turn through ``swarm.margot_bot.handle_turn``.

    Caller is responsible for delivering ``reply`` back to the user
    (this route does NOT send to Telegram — ``_send=False``).
    """
    _check_secret(x_pi_ceo_secret)

    # Lazy import — keeps the route importable in test envs without
    # the swarm dependencies wired up.
    try:
        from swarm.margot_bot import handle_turn  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — production deploy has swarm
        log.exception("margot_bot import failed")
        raise HTTPException(500, f"swarm.margot_bot unavailable: {exc}") from exc

    try:
        turn = await asyncio.wait_for(
            handle_turn(
                chat_id=body.chat_id,
                user_text=body.user_text,
                message_id=body.message_id,
                _send=False,
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError as exc:
        log.warning("margot_turn timeout chat_id=%s", body.chat_id)
        raise HTTPException(504, "Margot turn exceeded 120s timeout") from exc
    except Exception as exc:
        log.exception("margot_turn failed chat_id=%s", body.chat_id)
        raise HTTPException(500, f"Margot turn failed: {exc}") from exc

    return MargotTurnResponse(
        reply=turn.margot_text or "",
        cost_usd=float(turn.cost_usd or 0.0),
        research_called=bool(getattr(turn, "research_called", False)),
        board_session_ids=list(getattr(turn, "board_session_ids", []) or []),
        turn_id=str(getattr(turn, "turn_id", "")),
    )


# ── RA-1886: voice route ────────────────────────────────────────────────────


class MargotVoiceRequest(BaseModel):
    chat_id: str = Field(..., description="Telegram chat_id as string")
    file_id: str = Field(
        ..., min_length=1,
        description="Telegram file_id of the voice/audio attachment",
    )
    message_id: Optional[str] = Field(
        default=None, description="Telegram message_id (optional, for traceability)",
    )


class MargotVoiceResponse(BaseModel):
    reply: str
    transcript: str
    cost_usd: float
    research_called: bool
    board_session_ids: list[str]
    turn_id: str


def _resolve_telegram_token() -> str:
    """Read TELEGRAM_BOT_TOKEN from env. Used to download voice attachments."""
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


async def _download_telegram_file(file_id: str, *,
                                     dest_dir: Path) -> Path:
    """Resolve file_id → file_path via getFile, then download to dest_dir.

    Telegram Bot API two-step flow:
      1. GET https://api.telegram.org/bot<token>/getFile?file_id=...
         → returns {ok: true, result: {file_path: "voice/file_NN.oga"}}
      2. GET https://api.telegram.org/file/bot<token>/<file_path>
         → binary content of the file

    Raises HTTPException on any failure.
    """
    token = _resolve_telegram_token()
    if not token:
        raise HTTPException(
            503, "TELEGRAM_BOT_TOKEN not configured — cannot download voice",
        )

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            500, f"httpx unavailable for voice download: {exc}",
        ) from exc

    def _fetch_path() -> str:
        url = f"https://api.telegram.org/bot{token}/getFile"
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url, params={"file_id": file_id})
        if r.status_code >= 400:
            raise HTTPException(
                502, f"telegram getFile HTTP {r.status_code}: {r.text[:200]}",
            )
        body = r.json()
        if not body.get("ok"):
            raise HTTPException(
                502, f"telegram getFile not ok: {body.get('description', '?')}",
            )
        result = body.get("result") or {}
        path = result.get("file_path")
        if not path:
            raise HTTPException(502, "telegram getFile: missing file_path")
        return str(path)

    file_path = await asyncio.to_thread(_fetch_path)

    def _download() -> Path:
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        local = dest_dir / Path(file_path).name
        with httpx.Client(timeout=60.0) as client:
            with client.stream("GET", url) as r:
                if r.status_code >= 400:
                    raise HTTPException(
                        502,
                        f"telegram file download HTTP {r.status_code}",
                    )
                with local.open("wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        return local

    return await asyncio.to_thread(_download)


@router.post("/api/margot/voice", response_model=MargotVoiceResponse)
async def margot_voice_turn(
    body: MargotVoiceRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Drive one Margot voice turn — RA-1886.

    Pipeline:
      1. Download .ogg (or whatever audio format) from Telegram by file_id
      2. Transcribe via OpenRouter Whisper Large v3 Turbo
      3. Run handle_turn(transcript) — same enriched Margot pipeline
      4. Return reply + transcript so caller can echo the transcript back

    Caller responsible for delivering ``reply`` to Telegram (we set
    ``_send=False``).
    """
    _check_secret(x_pi_ceo_secret)

    try:
        from app.server.provider_whisper import transcribe  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — production deploy has it
        log.exception("provider_whisper import failed")
        raise HTTPException(
            500, f"provider_whisper unavailable: {exc}",
        ) from exc

    try:
        from swarm.margot_bot import handle_turn  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        log.exception("margot_bot import failed")
        raise HTTPException(500, f"swarm.margot_bot unavailable: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="margot-voice-") as tmpdir:
        dest = Path(tmpdir)
        try:
            audio_path = await asyncio.wait_for(
                _download_telegram_file(body.file_id, dest_dir=dest),
                timeout=70.0,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(504, "voice download exceeded 70s") from exc

        rc, transcript, _cost, error = await transcribe(
            audio_path, role="margot.voice",
            session_id=body.message_id or "",
        )
        if rc != 0 or error or not transcript:
            log.warning(
                "margot_voice: transcribe failed chat=%s err=%s",
                body.chat_id, error,
            )
            raise HTTPException(
                502, f"whisper transcription failed: {error or 'empty'}",
            )

        try:
            turn = await asyncio.wait_for(
                handle_turn(
                    chat_id=body.chat_id,
                    user_text=transcript,
                    message_id=body.message_id,
                    _send=False,
                ),
                timeout=120.0,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                504, "Margot voice turn exceeded 120s timeout",
            ) from exc
        except Exception as exc:
            log.exception("margot_voice handle_turn failed chat=%s", body.chat_id)
            raise HTTPException(
                500, f"Margot voice turn failed: {exc}",
            ) from exc

    return MargotVoiceResponse(
        reply=turn.margot_text or "",
        transcript=transcript,
        cost_usd=float(turn.cost_usd or 0.0),
        research_called=bool(getattr(turn, "research_called", False)),
        board_session_ids=list(getattr(turn, "board_session_ids", []) or []),
        turn_id=str(getattr(turn, "turn_id", "")),
    )
