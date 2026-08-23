"""Shared contracts and integrity primitives for Grill session modules."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
SHARED_UNDERSTANDING_PHRASE = "I confirm this is our shared understanding."
DECISION_RESOLUTIONS = frozenset({"DECIDED", "RABBIT_HOLE", "NO_GO"})
LEAF_KINDS = frozenset({"human-decision", "evidence-fact"})
EVIDENCE_RESOLUTION = "EVIDENCED"


class GrillSessionError(ValueError):
    """Raised when a Grill-Me transition fails closed."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GrillSessionError(f"{label} must be non-empty text")
    return value


def _without_integrity(session: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(session))
    candidate.pop("session_integrity_digest", None)
    return candidate


def _bind_integrity(session: dict[str, Any]) -> dict[str, Any]:
    session["session_integrity_digest"] = digest(_without_integrity(session))
    return session


def _normalise_domain_updates(
    updates: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    normalised: list[dict[str, str]] = []
    for index, raw in enumerate(updates or ()):
        if not isinstance(raw, Mapping):
            raise GrillSessionError(f"domain_updates[{index}] must be an object")
        term = _nonempty_text(raw.get("term"), f"domain_updates[{index}].term")
        meaning = _nonempty_text(raw.get("meaning"), f"domain_updates[{index}].meaning")
        normalised.append({"term": term, "meaning": meaning})
    return normalised
