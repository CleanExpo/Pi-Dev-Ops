"""Pure helpers for scripts/mission_control_jev_shadow.py, split out to keep it under the 300-line convention.

The shadow script re-exports every name here, so `from scripts.mission_control_jev_shadow import validate_answer`
keeps working."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from jev_platform import spend


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
    """Legacy ledgers gain the canonical row id and call id. The watcher skips a mirrored row only when its
    call id is in today's machine ledger: a row id alone is reused after the machine ledger is reset."""
    for name, kind in (("spend_id", "INTEGER"), ("spend_call_id", "TEXT")):
        spend.add_column(db, name, kind)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS calls_spend_call_id ON calls(spend_call_id)")


def link_own_row(ledger: Path, call_id: str, sql: str, params: tuple) -> None:
    """Update this tool's own row for one call, matched by its never-reused call id. No row means this ledger was
    reset mid-call: that is reported, never applied to whichever call holds the row id now (Codex round 4)."""
    with sqlite3.connect(ledger, timeout=30) as db:
        if db.execute(sql, params).rowcount != 1:
            print(f"jev shadow: own ledger has no row for call {call_id} (reset?)", file=sys.stderr)


_SPEND_IDS: dict[tuple[str, str], int] = {}  # (ledger, machine call id) -> machine row, settled first


def finish_call(ledger: Path, call_id: str, status: str, input_tokens: object = None) -> None:
    """Settle the machine row, then this ledger best-effort (a failure after a paid reply is logged and the row
    keeps its reserve), both by call id: a reset mid-call leaves the call that reused the row id untouched.

    input_tokens goes through the one settlement validator (spend.valid_tokens): missing, negative, oversized or
    mistyped usage leaves actual NULL and the reserve counted, never a settle above the reserve or a lowered total."""
    tokens = spend.valid_tokens(input_tokens)
    actual = tokens * spend.USD_PER_TOKEN if tokens is not None else None
    if (machine := _SPEND_IDS.pop((str(ledger), call_id), None)) is not None:
        spend.finish(machine, status, actual, tokens, call_id=call_id)
    try:
        with sqlite3.connect(ledger, timeout=30) as db:
            n = db.execute("UPDATE calls SET status=?, input_tokens=?, actual_usd=? WHERE spend_call_id=?",
                           (status, tokens, actual, call_id)).rowcount
        if n != 1:
            print(f"jev shadow: own ledger has no row for call {call_id} (reset?)", file=sys.stderr)
    except sqlite3.Error as exc:
        print(f"jev shadow: own ledger settle failed for call {call_id}: {type(exc).__name__}", file=sys.stderr)
