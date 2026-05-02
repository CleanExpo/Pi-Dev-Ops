"""swarm/bots/margot.py — Wave 5.1: Margot bot wrapper.

Thin shim over swarm.margot_bot for the orchestrator-side integration
path. The CoS bot's intent_router classifies inbound Telegram as
``intent="margot"`` and calls ``handle_telegram_intent(intent_payload)``
here, which extracts the prompt + chat_id and runs an asyncio event-loop
to invoke margot_bot.handle_turn.

This wrapper exists so the existing CoS-bot codebase can integrate via a
sync call rather than every CoS path needing to be async-aware.

Public API:
  handle_telegram_intent(intent_payload) -> dict
      Returns {"status": "ok"|"failed", "turn_id", "board_session_ids"}
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .. import margot_bot as _margot

log = logging.getLogger("swarm.bots.margot")

REPO_ROOT = Path(__file__).resolve().parents[2]


def handle_telegram_intent(payload: dict[str, Any], *,
                            repo_root: Path | None = None,
                            _send: bool = True) -> dict[str, Any]:
    """Process one inbound margot-intent Telegram message.

    payload follows the intent_router output shape:
      {
        "intent": "margot",
        "fields": {"prompt": "...", "addressed_by": "prefix"|"dm_chat"},
        "originating_chat_id": "...",
        "originating_message_id": "...",
        ...
      }
    """
    rr = repo_root or REPO_ROOT
    chat_id = payload.get("originating_chat_id")
    message_id = payload.get("originating_message_id")
    prompt = ((payload.get("fields") or {}).get("prompt")
               or payload.get("raw_message") or "").strip()

    if not chat_id or not prompt:
        return {"status": "failed",
                 "reason": "missing chat_id or prompt"}

    try:
        turn = asyncio.run(_margot.handle_turn(
            chat_id=str(chat_id),
            user_text=prompt,
            message_id=message_id,
            repo_root=rr,
            _send=_send,
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("margot bot: handle_turn raised (%s)", exc)
        return {"status": "failed", "reason": str(exc)}

    return {
        "status": "ok" if not turn.error else "failed",
        "turn_id": turn.turn_id,
        "board_session_ids": turn.board_session_ids,
        "error": turn.error,
    }


__all__ = ["handle_telegram_intent"]
