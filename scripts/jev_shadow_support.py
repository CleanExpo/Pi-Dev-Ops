"""Pure helpers for scripts/mission_control_jev_shadow.py, split out to keep it under the 300-line convention.

The shadow script re-exports every name here, so `from scripts.mission_control_jev_shadow import validate_answer`
keeps working."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def validate_answer(name: str, answer: object, question: dict) -> dict | None:
    if not isinstance(answer, dict) or answer.get("type") != question["type"]:
        return None
    if question["type"] == "noul":
        value = answer.get("noul")
        return {"probability": value} if type(value) in (float, int) and 0 <= value <= 1 else None
    probabilities, confidence = answer.get("probabilities"), answer.get("confidence")
    if not isinstance(probabilities, dict) or type(confidence) not in (float, int) or not 0 <= confidence <= 1:
        return None
    expected = set(question["criteria"] if question["type"] == "choice" else map(str, range(len(question["criteria"]))))
    if set(probabilities) != expected or any(type(value) not in (float, int) or not 0 <= value <= 1 for value in probabilities.values()):
        return None
    if abs(sum(probabilities.values()) - 1) > 0.02:
        return None
    if question["type"] == "choice":
        choice = answer.get("choice")
        if choice not in expected:
            return None
        return {"label": choice, "probabilities": probabilities, "confidence": confidence}
    score = answer.get("score")
    if type(score) not in (float, int) or not 0 <= score <= len(expected) - 1:
        return None
    return {"score": score, "probabilities": probabilities, "confidence": confidence}


def _caller(ledger: Path) -> str:
    return "skill_router" if ledger.name == "skill-router-ledger.sqlite" else "mission_control_jev_shadow"


def _ensure_spend_id(db: sqlite3.Connection) -> None:
    """Legacy ledgers gain the canonical row id, so the watcher counts a mirrored call once."""
    if "spend_id" not in {row[1] for row in db.execute("PRAGMA table_info(calls)")}:
        db.execute("ALTER TABLE calls ADD COLUMN spend_id INTEGER")
