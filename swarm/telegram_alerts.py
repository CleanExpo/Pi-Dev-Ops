"""
swarm/telegram_alerts.py — RA-650 / RA-2232: Swarm Telegram notification layer.

Historical single-bot API. As of RA-2232 this module is a thin shim over
``swarm.telegram_router`` — every call routes to the 'general' channel
(Margot, Phill's home inbox). New call sites should call
``swarm.telegram_router.send`` directly with an explicit ``channel=`` so
specialist categories (dev / ops / marketing / research) reach the right
bot.

All messages still receive the board-mandated [AGENT OUTPUT] prefix and
severity glyph; that formatting is now centralised in the router so any
direct router-callers get identical output.

Fire-and-forget: errors are logged at WARNING, never raised.
"""
from __future__ import annotations

import logging
from typing import Literal

from .telegram_router import send as _router_send

log = logging.getLogger("swarm.telegram")

Severity = Literal["critical", "high", "medium", "info"]


def send(
    message: str,
    severity: Severity = "info",
    bot_name: str = "Swarm",
) -> bool:
    """Send a Telegram message to the 'general' channel (Margot inbox).

    Back-compat shim — preserves the original positional/keyword signature so
    every existing caller in swarm/bots/*, swarm/orchestrator.py, etc keeps
    working unchanged. Delegates to ``telegram_router.send`` under the hood.

    Args:
        message:  Human-readable message body.
        severity: Escalation tier (critical/high/medium/info).
        bot_name: Which bot is sending (Guardian/Builder/Scribe/Click/…).

    Returns:
        True if the message was sent, False on any error.
    """
    return _router_send(
        message,
        channel="general",
        severity=severity,
        bot_name=bot_name,
    )


def send_daily_report(report_lines: list[str]) -> bool:
    """Format and send the daily 08:00 AEST swarm status report to general.

    Args:
        report_lines: Bullet-point lines for the report body.

    Returns:
        True if sent successfully.
    """
    body = "\n".join(f"• {line}" for line in report_lines)
    return send(
        message=f"<b>Daily Swarm Status Report</b>\n\n{body}",
        severity="info",
        bot_name="Orchestrator",
    )
