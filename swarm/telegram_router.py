"""swarm/telegram_router.py — RA-2232: multi-bot Telegram router.

Replaces the single-bot pattern with channel-typed routing. Each logical
channel (general / research / dev / ops / marketing) has its own bot token
and chat id, configured via env. Callers pass a channel name; the router
picks the right (token, chat_id) tuple. Falls back to the general channel
(Margot) with a "[fallback from <channel>]" prefix when a specialist
channel isn't configured — gradual onboarding without breaking anything.

Env-var layout (Australian English in the docs, US in the env names):

    general    | TELEGRAM_BOT_TOKEN           | TELEGRAM_HOME_CHANNEL
                                              |   (or legacy TELEGRAM_ALERT_CHAT_ID)
    research   | TELEGRAM_BOT_TOKEN_RESEARCH  | TELEGRAM_CHAT_ID_RESEARCH
    dev        | TELEGRAM_BOT_TOKEN_DEV       | TELEGRAM_CHAT_ID_DEV
    ops        | TELEGRAM_BOT_TOKEN_OPS       | TELEGRAM_CHAT_ID_OPS
    marketing  | TELEGRAM_BOT_TOKEN_MARKETING | TELEGRAM_CHAT_ID_MARKETING

Usage:

    from swarm.telegram_router import send

    # Implicit channel = general (back-compat).
    send("Hello", severity="info", bot_name="Margot")

    # Explicit channel.
    send("PR opened: feature_orchestrator → IDD-3 → RA-4180",
         channel="dev", severity="info", bot_name="FeatureOrchestrator")
    send("Watchdog: oldest urgent ticket 36h old",
         channel="ops", severity="high", bot_name="Watchdog")

This module deliberately mirrors the existing ``telegram_alerts.send``
formatting (AGENT OUTPUT prefix, severity glyphs, AEST timestamp, shadow
mode tag) so callers can opt-in to channel routing without changing the
shape of their messages. Fire-and-forget: errors are logged at WARNING,
never raised.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from . import config

log = logging.getLogger("swarm.telegram_router")

AEST = timezone(timedelta(hours=10))

Channel = Literal["general", "research", "dev", "ops", "marketing"]
ALL_CHANNELS: tuple[Channel, ...] = (
    "general", "research", "dev", "ops", "marketing",
)

Severity = Literal["critical", "high", "medium", "info"]

_SEVERITY_PREFIX: dict[str, str] = {
    "critical": "🚨 CRITICAL",
    "high":     "⚠️  HIGH",
    "medium":   "ℹ️  MEDIUM",
    "info":     "💬 INFO",
}


@dataclass(frozen=True)
class ChannelConfig:
    """Resolved (token, chat_id) for a logical channel."""
    name: Channel
    token: Optional[str]
    chat_id: Optional[str]

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)


def _load_channel(name: Channel) -> ChannelConfig:
    """Resolve env vars for a channel.

    'general' is special-cased to read the legacy TELEGRAM_BOT_TOKEN +
    TELEGRAM_HOME_CHANNEL (preferred) or TELEGRAM_ALERT_CHAT_ID (legacy
    fallback) so the existing Margot bot keeps working unchanged.
    """
    if name == "general":
        return ChannelConfig(
            name="general",
            token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            chat_id=(
                os.environ.get("TELEGRAM_HOME_CHANNEL")
                or os.environ.get("TELEGRAM_ALERT_CHAT_ID")
                or None
            ),
        )
    upper = name.upper()
    return ChannelConfig(
        name=name,
        token=os.environ.get(f"TELEGRAM_BOT_TOKEN_{upper}") or None,
        chat_id=os.environ.get(f"TELEGRAM_CHAT_ID_{upper}") or None,
    )


def configured_channels() -> list[Channel]:
    """Diagnostic — which channels currently have both token + chat_id set."""
    return [c for c in ALL_CHANNELS if _load_channel(c).configured]


def _format_body(
    message: str,
    severity: Severity,
    bot_name: str,
    fallback_from: Optional[Channel] = None,
) -> str:
    """Apply the board-mandated AGENT OUTPUT prefix + severity glyph + AEST stamp.

    Mirrors telegram_alerts.send so call sites that swap over to the router
    produce identical-looking messages.
    """
    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
    shadow_tag = " [SHADOW MODE]" if config.SHADOW_MODE else ""
    fallback_tag = f" [fallback from {fallback_from}]" if fallback_from else ""
    prefix = _SEVERITY_PREFIX.get(severity, "💬 INFO")
    return (
        f"[AGENT OUTPUT]{shadow_tag}{fallback_tag} — {prefix}\n"
        f"Bot: {bot_name} | {now}\n"
        f"\n{message}"
    )


def _post(token: str, chat_id: str, text: str, parse_mode: str) -> bool:
    """POST to the Telegram Bot API. Returns True on HTTP 200, False otherwise.

    Uses urllib so the router carries no extra dependency over the legacy
    telegram_alerts module.
    """
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001 — fire-and-forget
        log.warning("Telegram send failed (token=%s…): %s", token[:8], exc)
        return False


def send(
    message: str,
    *,
    channel: Channel = "general",
    severity: Severity = "info",
    bot_name: str = "Swarm",
    parse_mode: str = "HTML",
) -> bool:
    """Send ``message`` to the named ``channel``.

    Falls back to ``general`` with a "[fallback from <channel>]" tag when
    the requested channel has no token/chat_id configured. Returns True if
    the message landed on Telegram, False on any error (including
    "no channel configured at all").

    Keyword-only after ``message`` so call sites read naturally:

        send("PR merged", channel="dev", severity="info", bot_name="Builder")
    """
    cfg = _load_channel(channel)
    if not cfg.configured:
        if channel != "general":
            log.warning(
                "telegram channel %s not configured — falling back to general",
                channel,
            )
            # Recurse into general with a fallback-tag so Phill can see which
            # specialist channel hasn't been minted yet without scanning logs.
            general = _load_channel("general")
            if not general.configured:
                log.debug(
                    "Telegram not configured (general missing) — "
                    "suppressing alert: %s", message[:80],
                )
                return False
            body = _format_body(message, severity, bot_name, fallback_from=channel)
            return _post(general.token or "", general.chat_id or "", body, parse_mode)
        log.debug(
            "Telegram not configured (general missing) — suppressing alert: %s",
            message[:80],
        )
        return False

    body = _format_body(message, severity, bot_name)
    return _post(cfg.token or "", cfg.chat_id or "", body, parse_mode)


__all__ = [
    "Channel",
    "ChannelConfig",
    "ALL_CHANNELS",
    "configured_channels",
    "send",
]
