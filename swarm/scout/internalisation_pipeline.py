"""Scout → Synthex internalisation bridge.

A Scout-filed Linear ticket tagged 'internalise-via-synthex' is converted
into a Synthex content-brief that names an operator, holds the verdict to
the last 20%, and is checked against the brand-guardian forbidden words.

The brief is a HANDOFF dict; Synthex consumes it via its content-generation
pipeline. This module never writes content directly — it specifies what
content Synthex should produce.
"""
from __future__ import annotations
from typing import TypedDict


class SynthexBrief(TypedDict):
    title: str
    source_scout_id: str
    voice_spec: str
    named_operator: str  # e.g., "Karen — five-van Caboolture crew"
    verdict_position: str  # "last_20_percent"
    forbidden_words_check: bool
    competitor_artefact: str
    angle: str  # how WE address the topic, not how they did


def generate_synthex_brief(scout_ticket: dict) -> SynthexBrief:
    """Generate a Synthex content brief from a tagged Scout ticket."""
    return SynthexBrief(
        title=f"Our voice on: {scout_ticket['title']}",
        source_scout_id=scout_ticket["id"],
        voice_spec="nexus-human-voice-2026-05-11",
        named_operator="(specify a real operator per the voice spec — Karen / Toby / a foreman in $TOWN)",
        verdict_position="last_20_percent",
        forbidden_words_check=True,
        competitor_artefact=scout_ticket.get("body", ""),
        angle="our differentiator vs the competitor — what they got wrong, what we do instead",
    )
