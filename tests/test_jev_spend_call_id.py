"""Every Jev spend row carries a call id that is never reused (.claude/done/spm/2026-10-28-jev-spend-call-id/spec.md).

The Guardian watcher skips a mirrored legacy row only when its call id is in today's machine ledger. A row id
alone is reused after the machine ledger is reset, which let one $12 call hide another.
"""
import re
import sqlite3

from jev_platform import spend
from scripts import mission_control_jev_shadow as shadow
from tests.jev_spend_support import ledger, rows

HEX32 = re.compile(r"[0-9a-f]{32}")
OLD_SCHEMA = ("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, caller TEXT NOT NULL, "
              "reserved_usd REAL NOT NULL, actual_usd REAL, input_tokens INTEGER, status TEXT NOT NULL, "
              "created_at TEXT NOT NULL)")


def test_every_row_gets_its_own_call_id():
    spend.reserve("t", 1.0)
    spend.reserve("t", 1.0)
    ids = [r["call_id"] for r in rows()]
    assert len(ids) == 2 and all(HEX32.fullmatch(i or "") for i in ids) and ids[0] != ids[1], ids


def test_reserve_still_returns_the_row_id_and_reserve_call_returns_the_call_id_too():
    first = spend.reserve("t", 1.0)
    row, call_id = spend.reserve_call("t", 1.0)
    assert type(first) is int and type(row) is int and row == first + 1
    assert rows()[1]["call_id"] == call_id


def test_a_ledger_written_before_call_ids_is_upgraded_in_place():
    path = ledger()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(OLD_SCHEMA)
        db.execute("INSERT INTO calls(day, caller, reserved_usd, status, created_at) "
                   "VALUES ('2026-10-27', 'old', 3.5, 'answered', 'x')")
    _, call_id = spend.reserve_call("t", 1.0)
    old, new = rows()
    assert (old["caller"], old["reserved_usd"], old["call_id"]) == ("old", 3.5, None)
    assert new["call_id"] == call_id


def test_call_ids_are_unique_in_the_ledger():
    spend.reserve("t", 1.0)
    db = sqlite3.connect(ledger())
    try:
        dup = rows()[0]["call_id"]
        try:
            db.execute("INSERT INTO calls(day, caller, reserved_usd, status, created_at, call_id) "
                       "VALUES ('d', 'c', 1, 'attempted', 'x', ?)", (dup,))
        except sqlite3.IntegrityError:
            return
    finally:
        db.close()
    raise AssertionError("a second row with the same call id was accepted")


def test_the_mirrored_legacy_row_stores_its_machine_rows_call_id(tmp_path):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    own = shadow.reserve_call(legacy, 1000, cap=None)
    machine = rows()[0]
    with sqlite3.connect(legacy) as db:
        spend_id, spend_call_id = db.execute("SELECT spend_id, spend_call_id FROM calls WHERE id=?", (own,)).fetchone()
    assert (spend_id, spend_call_id) == (machine["id"], machine["call_id"]) and HEX32.fullmatch(spend_call_id)


def test_after_a_machine_ledger_reset_a_reused_row_id_gets_a_new_call_id(tmp_path):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    shadow.reserve_call(legacy, 1000, cap=None)
    before = rows()[0]
    ledger().unlink()
    shadow.reserve_call(legacy, 1000, cap=None)
    after = rows()[0]
    assert after["id"] == before["id"] and after["call_id"] != before["call_id"]
    with sqlite3.connect(legacy) as db:
        mirrored = [r[0] for r in db.execute("SELECT spend_call_id FROM calls ORDER BY id")]
    assert mirrored == [before["call_id"], after["call_id"]]
