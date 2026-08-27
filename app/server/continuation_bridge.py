"""Internal Mission Control continuation bridge for Telegram and Margot.

Every Telegram text update refreshes the canonical execution objective, and
every Margot prompt receives the rolling 15-step continuation contract. No new
public API surface is created here. Existing approval, kill-switch, spend,
deploy, merge and deletion gates remain authoritative.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .continuation_horizon import arm_objective, operator_context

log = logging.getLogger("pi-ceo.continuation_bridge")
_PATCHED = False


def _telegram_text(update: dict[str, Any]) -> tuple[str, str]:
    msg = update.get("message") if isinstance(update, dict) else None
    if not isinstance(msg, dict):
        return "", ""
    text = str(msg.get("text") or "").strip()
    chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
    return text, str(chat.get("id") or "")


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
        return f"{operator_context()}\n\n{original(*args, **kwargs)}"
    return wrapped


def install_continuation_bridge() -> bool:
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from .routes import webhooks
        from swarm import margot_bot

        webhooks._drain_telegram_update = _wrap_telegram_drain(webhooks._drain_telegram_update)
        margot_bot.build_prompt = _wrap_margot_prompt(margot_bot.build_prompt)
        _PATCHED = True
        log.info("Mission Control continuation bridge installed for Telegram + Margot")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Mission Control continuation bridge unavailable: %s", exc, exc_info=True)
        return False
