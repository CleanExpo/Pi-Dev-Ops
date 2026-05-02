"""
swarm/intent_router.py — RA-1839: CoS intent classifier.

Implements the 6-intent classification spec from
Pi-Dev-Ops/skills/intent-parser/SKILL.md.

Layer 1 — regex fast path (this file).
Layer 2 — Claude classification fallback (stub; wired in next session).

Output schema is the canonical intent payload that downstream skills
(margot-bridge, telegram-draft-for-review, dispatcher-core) consume.

Kill-switch behaviour: this module is pure — no I/O, no network. It
returns intent decisions; routing is the caller's job. The orchestrator
loop's TAO_SWARM_ENABLED check still gates whether the decision becomes
an action.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

log = logging.getLogger("swarm.intent_router")

Intent = Literal[
    "research", "ticket", "reply", "reminder", "flow",
    "margot",     # Wave 5.1 — conversational personal-assistant turn
    "unknown",
]

# ── PII guard regexes (forced unknown if any hit) ────────────────────────────
_LUHN_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_API_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|claude-api-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b")

# ── Per-intent regexes (high precision, low recall — Claude classify is fallback) ──
_RESEARCH_PATTERNS = [
    re.compile(r"\b(what'?s|find|research|look up|check|tell me about|deep dive|deep-dive)\b", re.I),
    re.compile(r"\bwhere (can|do) I find\b", re.I),
    re.compile(r"\b(?:please )?(?:give me|get me) (?:the )?(?:latest|context)\b", re.I),
]
_RESEARCH_DEEP_HINTS = re.compile(r"\b(deep dive|deep-dive|long form|long-form|full report|max|comprehensive)\b", re.I)

_TICKET_PATTERNS = [
    re.compile(r"\b(file|create|open|track|raise) (a )?(linear )?(ticket|issue|p\d|bug)\b", re.I),
    re.compile(r"\bnew (issue|bug|ticket)\b", re.I),
    re.compile(r"\b(can you|please) (file|create|open|raise)\b.*(?:ticket|issue|bug)", re.I),
]
_TICKET_TEAM_RE = re.compile(r"\b(in|for|on)\s+(RA|GP|SYN|UNI|DR|RestoreAssist|CARSI|Synthex|Unite|Pi-Dev-Ops)\b", re.I)

_REPLY_PATTERNS = [
    re.compile(r"\b(tell|message|reply|respond|draft)\b.*\b(to|for)\s+\w+", re.I),
    re.compile(r"\bdraft (an? )?(reply|response|message)\b", re.I),
    re.compile(r"\bask\s+(margot|gpt|claude)\s+to\b", re.I),
]

_REMINDER_PATTERNS = [
    re.compile(r"\b(remind|nudge|chase) me\b", re.I),
    re.compile(r"\bset a reminder\b", re.I),
    re.compile(r"\bwake me up\b.*\b(at|on)\s+\d", re.I),
]

_FLOW_PATTERNS = [
    re.compile(r"\b(first|step 1|then|after that)\b.*\b(then|step \d|after that|finally)\b", re.I),
    re.compile(r"\brun the (\w+ )?flow\b", re.I),
    re.compile(r"\b/flow\b", re.I),
]

# ── Margot personal-assistant addressing (Wave 5.1) ──────────────────────────
# Three triggers (matched in order, highest priority first):
#   1. Explicit prefix: "Margot, ..." / "@margot" / "/margot"
#   2. Whole-message DM in MARGOT_DM_CHAT_ID env (configured per deploy)
#   3. (Wave 6) dedicated MargotBot username
_MARGOT_PREFIX_PATTERNS = [
    re.compile(r"^\s*margot[,:\s]", re.I),
    re.compile(r"^\s*@margot\b", re.I),
    re.compile(r"^\s*/margot\b", re.I),
    re.compile(r"\bhey\s+margot\b", re.I),
]


def _is_margot_dm_chat(chat_id: str | None) -> bool:
    """True when this chat_id is the configured Margot DM thread."""
    if not chat_id:
        return False
    target = (os.environ.get("MARGOT_DM_CHAT_ID") or "").strip()
    return bool(target) and str(chat_id) == target


def _strip_margot_prefix(text: str) -> str:
    """Remove the 'Margot, ' / '@margot ' / '/margot ' prefix from the
    message so the actual prompt is what flows downstream."""
    for pat in _MARGOT_PREFIX_PATTERNS:
        text = pat.sub("", text, count=1).lstrip()
    return text


def _has_pii(text: str) -> bool:
    """Return True if obvious high-risk PII is in the message."""
    if _SSN_RE.search(text) or _API_KEY_RE.search(text):
        return True
    for m in _LUHN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def _luhn_ok(digits: str) -> bool:
    """Validate a credit-card-shaped digit string with Luhn checksum."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _parse_relative_date(text: str, now: datetime) -> str | None:
    """Convert simple relative-date phrases to ISO-8601 in user-local TZ.

    Returns None if no parseable date is found. This is a deliberately
    narrow parser — `tomorrow`, `Mon..Sun`, `next week`, `in N hours`.
    Anything more complex defers to Claude classify.
    """
    t = text.lower()
    if "tomorrow" in t:
        target = now + timedelta(days=1)
        return target.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    if "tonight" in t:
        return now.replace(hour=20, minute=0, second=0, microsecond=0).isoformat()
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(weekdays):
        if day in t:
            today_idx = now.weekday()
            delta_days = (i - today_idx) % 7
            if delta_days == 0:
                delta_days = 7
            target = now + timedelta(days=delta_days)
            return target.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    m = re.search(r"in (\d+)\s*hours?", t)
    if m:
        return (now + timedelta(hours=int(m.group(1)))).isoformat()
    return None


def classify(
    message_text: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Classify a Telegram message into one of six intents.

    Returns the canonical intent payload. Confidence below 0.6 → unknown.
    """
    now = now or datetime.now(timezone.utc)
    text = (message_text or "").strip()
    base = {
        "intent": "unknown",
        "confidence": 0.0,
        "fields": {},
        "raw_message": text,
        "originating_chat_id": chat_id,
        "originating_message_id": message_id,
        "received_at": now.isoformat(),
    }

    if not text:
        return base

    if _has_pii(text):
        log.warning("PII detected in inbound — forcing intent=unknown")
        base["fields"]["pii_guard"] = True
        return base

    # ── Margot intent (highest priority — personal assistant addressing) ──
    margot_addressed = (
        any(p.search(text) for p in _MARGOT_PREFIX_PATTERNS)
        or _is_margot_dm_chat(chat_id)
    )
    if margot_addressed:
        prompt = _strip_margot_prefix(text) if any(
            p.search(text) for p in _MARGOT_PREFIX_PATTERNS
        ) else text
        return {
            **base, "intent": "margot", "confidence": 0.95,
            "fields": {
                "prompt": prompt,
                "addressed_by": (
                    "prefix"
                    if any(p.search(text) for p in _MARGOT_PREFIX_PATTERNS)
                    else "dm_chat"
                ),
            },
        }

    if any(p.search(text) for p in _FLOW_PATTERNS):
        return {**base, "intent": "flow", "confidence": 0.8,
                "fields": {"raw_steps_text": text}}

    if any(p.search(text) for p in _TICKET_PATTERNS):
        team_match = _TICKET_TEAM_RE.search(text)
        return {**base, "intent": "ticket", "confidence": 0.85,
                "fields": {
                    "team_hint": team_match.group(2) if team_match else None,
                    "title_hint": text[:80],
                }}

    if any(p.search(text) for p in _REMINDER_PATTERNS):
        when = _parse_relative_date(text, now)
        return {**base, "intent": "reminder", "confidence": 0.8 if when else 0.6,
                "fields": {"when": when, "what": text}}

    if any(p.search(text) for p in _REPLY_PATTERNS):
        return {**base, "intent": "reply", "confidence": 0.75,
                "fields": {"medium": "telegram", "body_hint": text}}

    if any(p.search(text) for p in _RESEARCH_PATTERNS):
        deep = bool(_RESEARCH_DEEP_HINTS.search(text))
        return {**base, "intent": "research", "confidence": 0.8,
                "fields": {
                    "topic": text,
                    "time_budget": "deep" if deep else "quick",
                    "use_corpus": True,
                }}

    return base


__all__ = ["classify", "Intent"]
