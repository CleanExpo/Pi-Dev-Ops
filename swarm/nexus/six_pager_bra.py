"""Render BRA reports into 6-pager + voice variants.

Phase B / B6. Pure-logic rendering — no LLM, no I/O. The
six_pager_dispatcher calls swarm.nexus.bra.generate_bra() per active
workspace, hands the report set here for rendering, then includes the
output in the daily Telegram message.

Voice variant collapses each card to ≤ VOICE_MAX_WORDS_PER_CARD so the
audio fits under MAX_VOICE_SECONDS at a normal speaking rate (~150 wpm).
"""
from __future__ import annotations

import re
from typing import Iterable

from .bra import BRACard, BRAReport

VOICE_MAX_WORDS_PER_CARD = 75  # ~30s at 150 wpm
SEVERITY_PREFIX = {
    "critical": "🚨",
    "high":     "🔴",
    "medium":   "🟡",
    "low":      "🟢",
    "info":     "ℹ️",
}


# ============================================================
# Markdown / Telegram block
# ============================================================


def render_bra_block(reports: Iterable[BRAReport]) -> str:
    """Compose the 6-pager BRA section as Telegram-friendly markdown.

    Empty / missing reports produce an empty string so the section can
    be omitted cleanly upstream.
    """
    reports = list(reports)
    if not reports:
        return ""

    lines: list[str] = ["8. Nexus BRA cards"]
    for report in reports:
        if not report.cards:
            lines.append(f"  • {report.workspace_slug}: no signals this window.")
            continue
        lines.append(f"  • {report.workspace_slug} ({report.window}):")
        for card in report.cards:
            lines.append(f"    {SEVERITY_PREFIX.get(card.severity, '')} {card.brief}")
            lines.append(f"        → {card.recommendation}")
            lines.append(f"        Action: {card.action}")
            lines.append(f"        Evidence: {', '.join(card.evidence_ids)}")
    return "\n".join(lines)


# ============================================================
# Voice variant — ≤30s per card
# ============================================================


def _truncate_words(text: str, max_words: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",.;:") + "…"


def _voice_phrase(card: BRACard) -> str:
    sentence = f"{card.brief} Recommendation: {card.recommendation}. Action: {card.action}."
    return _truncate_words(sentence, VOICE_MAX_WORDS_PER_CARD)


def render_bra_voice(reports: Iterable[BRAReport]) -> str:
    """Plain-text voice script for the BRA section.

    Each card is collapsed to ≤ VOICE_MAX_WORDS_PER_CARD words; emojis
    are dropped (they don't speak well). Empty inputs produce ''.
    """
    reports = [r for r in reports if r.cards]
    if not reports:
        return ""

    paragraphs: list[str] = ["Nexus BRA update."]
    for report in reports:
        paragraphs.append(f"For {report.workspace_slug}:")
        for card in report.cards:
            paragraphs.append(_voice_phrase(card))
    return " ".join(paragraphs)


__all__ = [
    "VOICE_MAX_WORDS_PER_CARD",
    "render_bra_block",
    "render_bra_voice",
]
