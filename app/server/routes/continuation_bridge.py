"""Mission Control continuation bridge for Telegram, Margot and dashboard status.

This module wraps existing seams instead of replacing them:
- every allowed Telegram text update arms/refreshes the shared objective ledger;
- every Margot prompt receives the rolling-horizon operating contract;
- Mission Control can read current continuation state through an auth-gated API.

The wrapper never executes protected actions. Existing approval, kill-switch,
spend, deploy, merge and deletion gates remain authoritative.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..continuation_horizon import arm_objective, load_state, operator_context

log = logging.getLogger("pi-ceo.continuation_bridge")
router = APIRouter(prefix="/api/continuation", tags=["continuation"])

_PATCHED = False


def _telegram_text(update: dict[str, Any]) -> tuple[str, str]:
    msg = update.get("message") if isinstance(update, dict) else None
    if not isinstance(msg, dict):
        return "", ""
    text = str(msg.get("text") or "").strip()
    chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    chat_id = str(chat.get("id") or "")
    return text, chat_id


def _wrap_telegram_drain(original: Callable[[dict], dict]) -> Callable[[dict], dict]:
    def wrapped(data: dict) -> dict:
        text, chat_id = _telegram_text(data)
        if text:
            try:
                arm_objective(objective=text, source="telegram", chat_id=chat_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("continuation horizon Telegram arm failed: %s", exc)
        return original(data)
    return wrapped


def _wrap_margot_prompt(original: Callable[..., str]) -> Callable[..., str]:
    def wrapped(*args: Any, **kwargs: Any) -> str:
        prompt = original(*args, **kwargs)
        return f"{operator_context()}\n\n{prompt}"
    return wrapped


def install_continuation_bridge() -> bool:
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from . import webhooks
        from swarm import margot_bot

        webhooks._drain_telegram_update = _wrap_telegram_drain(webhooks._drain_telegram_update)
        margot_bot.build_prompt = _wrap_margot_prompt(margot_bot.build_prompt)
        _PATCHED = True
        log.info("Mission Control continuation bridge installed for Telegram + Margot")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Mission Control continuation bridge unavailable: %s", exc, exc_info=True)
        return False


@router.get("/status", dependencies=[Depends(require_auth)])
async def continuation_status() -> dict[str, Any]:
    state = load_state()
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    pending = [s for s in steps if s.get("status") not in {"done", "verified", "complete"}]
    return {
        "armed": bool(state.get("armed")),
        "completed": bool(state.get("completed")),
        "source": state.get("source"),
        "objective": state.get("objective"),
        "chat_id": state.get("chat_id"),
        "horizon_target": state.get("horizon_target", 15),
        "steps": steps,
        "pending_count": len(pending),
        "updated_at": state.get("updated_at"),
    }


install_continuation_bridge()
