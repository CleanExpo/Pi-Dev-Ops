"""Linear description helpers for approved goal drafts."""
from __future__ import annotations

from typing import Any

_DRAFT_NOTE_FIELDS = (
    ("Context", "context"),
    ("User story", "user_story"),
    ("Current behaviour", "current_behaviour"),
    ("Expected behaviour", "expected_behaviour"),
    ("Technical requirements", "technical_requirements"),
    ("Edge cases", "edge_cases"),
    ("Testing", "testing"),
    ("Dependencies", "dependencies"),
    ("Why this ticket", "rationale"),
)


def format_draft_notes(draft: dict[str, Any]) -> str:
    """Markdown body for a Linear ticket from an approved draft."""
    chunks: list[str] = []
    for heading, key in _DRAFT_NOTE_FIELDS:
        body = str(draft.get(key) or "").strip()
        if body:
            chunks.append(f"## {heading}\n{body}")
    return "\n\n".join(chunks)
