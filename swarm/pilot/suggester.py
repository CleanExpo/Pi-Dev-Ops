"""Suggester — rank candidates; dedup against already-pending fingerprints.

Per glossary 'fingerprint': source-local string equality-match.
Cross-cycle dedup: a fingerprint already in pilot_suggestions with state='pending'
is excluded (prevents re-sending the same suggestion every cycle).
"""
from typing import Optional

from swarm.pilot.types import RawCandidate


def _score(c: RawCandidate) -> int:
    return c.impact_score


def _rank(candidates: list[RawCandidate], memory) -> Optional[RawCandidate]:
    allowed = [
        c for c in candidates
        if not memory.is_blocked(c.fingerprint)
        and not memory.has_pending_fingerprint(c.fingerprint)
    ]
    return max(allowed, key=_score) if allowed else None


def pick_top(memory) -> Optional[RawCandidate]:
    from swarm.pilot.sources import linear_source, margot_source, github_source
    candidates: list[RawCandidate] = []
    for src in (linear_source, margot_source, github_source):
        try:
            candidates.extend(src.collect())
        except Exception:
            pass
    return _rank(candidates, memory)
