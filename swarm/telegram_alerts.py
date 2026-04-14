"""
swarm/telegram_alerts.py — RA-650: Swarm Telegram notification layer.

All messages are prefixed with [AGENT OUTPUT] per the board's transparency
requirement.  Severity levels map to the board-approved escalation hierarchy.

Fire-and-forget: errors are logged at WARNING, never raised.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Literal

from . import config

log = logging.getLogger("swarm.telegram")

AEST = timezone(timedelta(hours=10))

Severity = Literal["critical", "high", "medium", "info"]

_SEVERITY_PREFIX: dict[str, str] = {
    "critical": "🚨 CRITICAL",
    "high":     "⚠️  HIGH",
    "medium":   "ℹ️  MEDIUM",
    "info":     "💬 INFO",
}


def send(
    message: str,
    severity: Severity = "info",
    bot_name: str = "Swarm",
) -> bool:
    """Send a Telegram message with the board-mandated AGENT OUTPUT prefix.

    Args:
        message:  Human-readable message body.
        severity: Escalation tier (critical/high/medium/info).
        bot_name: Which bot is sending (Guardian/Builder/Scribe/Click).

    Returns:
        True if the message was sent, False on any error.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        log.debug("Telegram not configured — suppressing alert: %s", message[:80])
        return False

    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
    shadow_tag = " [SHADOW MODE]" if config.SHADOW_MODE else ""
    prefix = _SEVERITY_PREFIX.get(severity, "💬 INFO")

    full_text = (
        f"[AGENT OUTPUT]{shadow_tag} — {prefix}\n"
        f"Bot: {bot_name} | {now}\n"
        f"\n{message}"
    )

    payload = json.dumps({
        "chat_id": chat_id,
        "text":    full_text,
        "parse_mode": "HTML",
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
    except Exception as exc:
        log.warning("Telegram send failed (severity=%s): %s", severity, exc)
        return False


def send_daily_report(report_lines: list[str]) -> bool:
    """Format and send the daily 08:00 AEST swarm status report.

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
