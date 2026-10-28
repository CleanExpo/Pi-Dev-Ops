"""Shared readers and fakes for tests/test_jev_spend_ledger.py (split out for the 300-line convention)."""
import io
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from jev_platform import client
from scripts import jev_triage as triage
from scripts import mission_control_jev_shadow as shadow

ROOT = Path(__file__).resolve().parents[1]
# The Guardian watcher's query, verbatim (skills/guardian/scripts/jev-cap-watcher.py).
WATCHER_SQL = "SELECT COALESCE(actual_usd, reserved_usd) FROM calls WHERE day=?"
PRICE = 0.042 / 1_000_000
BODY = {"state": "s", "model": "jev-latest", "questions": {}}
QUESTION = {"question": "Is it fine?", "criteria_true": "yes", "criteria_false": "no"}
SNAP = {"run_id": "r1", "sha": "abcdef1", "surface": "/x", "contract": "J1", "page_text": "hello", "network": []}
SHADOW_SNAP = {"run_id": "r1", "sha": "abcdef1", "surface": "/x", "visible_text": "hello", "data_classification": "synthetic"}


def ledger() -> Path:
    return Path(os.environ["JEV_SPEND_LEDGER"])


def rows(path: Path | None = None) -> list[dict]:
    path = path or ledger()
    if not path.exists():
        return []
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute("SELECT * FROM calls ORDER BY id")]
    finally:
        db.close()


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def watcher_sum(day: str, path: Path | None = None) -> float:
    db = sqlite3.connect(f"file:{path or ledger()}?mode=ro", uri=True)
    try:
        return sum(r[0] for r in db.execute(WATCHER_SQL, (day,)))
    finally:
        db.close()


def unwritable(tmp_path: Path, monkeypatch) -> None:
    """A ledger whose parent is a regular file: works as root and on every mount, unlike chmod."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("JEV_SPEND_LEDGER", str(blocker / "spend.sqlite"))


def budget() -> client.Budget:
    return client.Budget(1.0, 60)


def triage_ledger(tmp_path: Path) -> triage.Ledger:
    return triage.Ledger(tmp_path / "triage.json", today(), None)


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def shadow_reply(tokens: int = 100) -> _Reply:
    return _Reply(json.dumps({"model": shadow.MODEL, "answers": {}, "usage": {"input_tokens": tokens}}).encode())
