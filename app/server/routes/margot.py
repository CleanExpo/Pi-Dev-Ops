"""Margot bridge route — RA-1871.

Lets external callers (today: Hermes daemon's pi-ceo MCP server) drive a
single Margot turn through the Wave-4/5 ``swarm.margot_bot.handle_turn``
pipeline without owning the Telegram bot token themselves.

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
