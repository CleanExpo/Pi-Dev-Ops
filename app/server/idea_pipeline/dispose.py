"""One-word dispose and the GO gate. Nothing starts unless GO is explicit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import VERDICTS


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineGateError(ValueError):
    """Founder-facing refusal — dispose or GO was illegal."""


def normalize_verdict(word: str) -> str:
    verdict = (word or "").strip().upper()
    if verdict not in VERDICTS:
        raise PipelineGateError(
            "Dispose with one word: PROMOTE, BACKLOG, PARK, or KILL."
        )
    return verdict


def dispose(packet: dict[str, Any], word: str) -> dict[str, Any]:
    if packet.get("executed"):
        raise PipelineGateError("This idea already executed. It cannot be re-disposed.")
    verdict = normalize_verdict(word)
    updated = dict(packet)
    updated["verdict"] = verdict
    updated["status"] = "disposed"
    updated["disposed_at"] = _iso_now()
    updated["executed"] = False
    if verdict != "PROMOTE":
        updated["go_at"] = None
        updated["execution_requested"] = False
    return updated


def authorize_go(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("verdict") != "PROMOTE":
        raise PipelineGateError("GO is only allowed after PROMOTE.")
    updated = dict(packet)
    updated["go_at"] = _iso_now()
    updated["executed"] = False
    return updated


def try_execute(packet: dict[str, Any]) -> dict[str, Any]:
    """Record an execute request. Never starts a build. Refuses without GO."""
    if packet.get("verdict") != "PROMOTE":
        raise PipelineGateError("Only a PROMOTE idea can execute, and only after GO.")
    if not packet.get("go_at"):
        raise PipelineGateError("Nothing executes without GO.")
    updated = dict(packet)
    updated["execution_requested"] = True
    updated["executed"] = False
    return updated


def start_spec_pipeline(_packet: dict[str, Any]) -> dict[str, Any]:
    """Intentionally unused. Auto-start is out of scope for UNI-2633."""
    raise PipelineGateError("The idea pipeline does not auto-start a build.")
