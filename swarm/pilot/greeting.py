"""Greeting card — first-contact Telegram message with 2-row InlineKeyboardMarkup.

Per ADR 003 §3: embeds the suggestion card layout, documents both pause modes,
and explicitly states scope separation ("L4 digest runs regardless of pause-state").

Removes the V0 broken-contract phrase "Reply STOP to pause" (promised a handler
that never existed, surfaced as a gap in grill-output-pilot-bot-2026-05-15).
"""

# Sentinel fingerprint for greeting buttons — no suggestion associated.
_GREETING_FP = "greeting"

_ROW1 = [("✅ Agree", "agree"), ("❌ Dismiss", "dismiss"), ("🎙 Discuss", "discuss")]
_ROW2 = [("⏸ PAUSE 24h", "pause_24h"), ("⏹ STOP", "stop")]

_TEXT = (
    "👋 Pilot online. Suggestions stream 08:00–22:00 AEST.\n\n"
    "Each suggestion arrives as a card with two button rows:\n"
    "  Row 1: ✅ Agree · ❌ Dismiss · 🎙 Discuss (voice reply)\n"
    "  Row 2: ⏸ PAUSE 24h · ⏹ STOP\n\n"
    "PAUSE 24h — soft pause until tomorrow (auto-resumes).\n"
    "STOP — hard pause indefinitely. Send RESUME to re-enable.\n\n"
    "The daily L4 executive digest runs regardless of pause-state —\n"
    "you never blackhole yourself from awareness, only from interruption."
)


def first_contact_card() -> dict:
    """Return a Telegram sendMessage payload for the Pilot greeting card."""
    keyboard = [
        [{"text": label, "callback_data": f"{action}|{_GREETING_FP}"} for label, action in _ROW1],
        [{"text": label, "callback_data": f"{action}|{_GREETING_FP}"} for label, action in _ROW2],
    ]
    return {"text": _TEXT, "reply_markup": {"inline_keyboard": keyboard}}
