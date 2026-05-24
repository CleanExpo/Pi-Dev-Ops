"""Composer — sendMessage payload with 2-row InlineKeyboardMarkup.

Per ADR 003: Row 1 = Agree/Dismiss/Discuss; Row 2 = PAUSE 24h / STOP.
Per ADR 001: pillar rendered as chip-array.
Never emits plain text — every suggestion is a card.
"""
from swarm.pilot.types import RawCandidate

MAX_HEADLINE = 80
MAX_BODY = 500

_ROW1 = [("✅ Agree", "agree"), ("❌ Dismiss", "dismiss"), ("🎙 Discuss", "discuss")]
_ROW2 = [("⏸ PAUSE 24h", "pause_24h"), ("⏹ STOP", "stop")]


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _pillar_chips(pillars: list[str]) -> str:
    return " · ".join(f"[{p}]" for p in pillars)


def format(c: RawCandidate) -> dict:
    """Return a Telegram sendMessage payload dict with InlineKeyboardMarkup."""
    headline = _trunc(c.headline, MAX_HEADLINE)
    text = (
        f"{headline}\n\n"
        f"🎯 Pillar: {_pillar_chips(c.pillar)}\n"
        f"⚙️ Effort: {c.effort}\n"
        f"📂 Source: {c.source}\n"
        f"🔮 Confidence: {c.confidence}"
    )
    if len(text) > MAX_BODY:
        text = text[: MAX_BODY - 1].rstrip() + "…"
    keyboard = [
        [{"text": label, "callback_data": f"{action}|{c.fingerprint}"} for label, action in _ROW1],
        [{"text": label, "callback_data": f"{action}|{c.fingerprint}"} for label, action in _ROW2],
    ]
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}
