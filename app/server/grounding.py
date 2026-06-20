"""app/server/grounding.py — source-grounding primitive.

Stops generation-on-generation degradation: every derived artifact carries a
source anchor (back-pointer + content hash + TTL); reground() re-fetches the
primary source before the next generation, verifying hash + TTL and detecting
lineage cycles (the self-feeding-loop alarm). require_grounding() is the
enforced gate.

Pure functions; resolvers are injectable for tests. Spec:
docs/superpowers/specs/2026-06-21-grounding-primitive-design.md
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)

FRESH = "FRESH"
DRIFTED = "DRIFTED"
STALE = "STALE"
MISSING = "MISSING"
CYCLE = "CYCLE"

DEFAULT_TTL_HOURS = 168


class GroundingError(Exception):
    """Raised by require_grounding when an artifact is not FRESH."""


@dataclass
class GroundResult:
    status: str
    primary_text: str | None = None
    primary_uri: str | None = None
    chain: list[str] = field(default_factory=list)
    detail: str = ""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record(
    *,
    primary_source: str,
    derived_from: str | list[str],
    parent_text: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    confidence: float | None = None,
    parent_chain: list[str] | None = None,
) -> dict:
    """Build a source-anchor dict for a derived artifact.

    parent_text is the immediate parent's current content, hashed for drift
    detection. parent_chain is the parent's own lineage; the returned chain
    appends this hop's immediate parent so reground() can detect cycles. The
    caller persists the returned dict (frontmatter for markdown, fenced block
    for ticket/JSONL bodies).
    """
    first_parent = derived_from if isinstance(derived_from, str) else derived_from[0]
    anchor: dict = {
        "primary_source": primary_source,
        "derived_from": derived_from,
        "source_sha256": _sha256_hex(parent_text.encode("utf-8")),
        "derived_at": _utcnow().isoformat(),
        "ttl_hours": ttl_hours,
        "chain": list(parent_chain or []) + [first_parent],
    }
    if confidence is not None:
        anchor["confidence"] = confidence
    return anchor
