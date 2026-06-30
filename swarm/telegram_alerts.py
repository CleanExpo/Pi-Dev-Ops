"""
swarm/telegram_alerts.py — RA-650: Swarm Telegram notification layer.

All messages are prefixed with [AGENT OUTPUT] per the board's transparency
requirement.  Severity levels map to the board-approved escalation hierarchy.

Fire-and-forget: errors are logged at WARNING, never raised.
"""
from __future__ import annotations

import json
import logging
import os
import re
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


def _alert_state_path():
    return config.SWARM_LOG_DIR / "telegram_alert_state.json"


def _alert_signature(severity: str, message: str) -> str:
    """Stable signature of an alert with volatile numbers stripped.

    Mirrors the Guardian edge-trigger (RA-6655): "3.2h old" and "3.3h old"
    collapse to the same condition so a persistent state pages once, not
    every cycle. Two sends with the same severity and the same underlying
    message produce the same signature.
    """
    norm = re.sub(r"[\d.]+", "#", message)
    return json.dumps([severity, norm], sort_keys=True)


def _load_alert_state() -> dict:
    try:
        return json.loads(_alert_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_alert_state(state: dict) -> None:
    try:
        _alert_state_path().write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram: could not persist alert state: %s", exc)


def send(
    message: str,
    severity: Severity = "info",
    bot_name: str = "Swarm",
    dedup_key: str | None = None,
) -> bool:
    """Send a Telegram message with the board-mandated AGENT OUTPUT prefix.

    Args:
        message:  Human-readable message body.
        severity: Escalation tier (critical/high/medium/info).
        bot_name: Which bot is sending (Guardian/Builder/Scribe/Click).
        dedup_key: When set, edge-trigger this alert. A persistent condition
            (same severity + same message, ignoring volatile numbers) pages
            once; the alert re-fires only when its state genuinely changes.
            Prevents the per-cycle [AGENT OUTPUT] spam the founder has zero
            tolerance for. Stateless callers should pass this; callers that
            keep their own suspend/escalation state (Guardian, Orchestrator)
            need not.

    Returns:
        True if the message was sent, False on any error or suppression.
    """
    # Fail-closed kill-switch (founder directive 2026-06-15): every
    # [AGENT OUTPUT] Telegram alert is suppressed unless explicitly
    # re-enabled. Per-cycle CRITICAL spam is a zero-tolerance violation
    # of the edge-trigger rule; sends stay off until edge-triggering is
    # implemented and the founder flips SWARM_TELEGRAM_ALERTS back on.
    if os.environ.get("SWARM_TELEGRAM_ALERTS", "").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        log.debug("Telegram alerts disabled (SWARM_TELEGRAM_ALERTS off): %s", message[:80])
        return False

    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        log.debug("Telegram not configured — suppressing alert: %s", message[:80])
        return False

    # Edge-trigger: skip a re-send when this keyed alert's state is unchanged.
    sig = None
    if dedup_key is not None:
        sig = _alert_signature(severity, message)
        if _load_alert_state().get(dedup_key) == sig:
            log.debug("Telegram alert unchanged — suppressing (dedup_key=%s)", dedup_key)
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
        if dedup_key is not None and sig is not None:
            state = _load_alert_state()
            state[dedup_key] = sig
            _save_alert_state(state)
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
