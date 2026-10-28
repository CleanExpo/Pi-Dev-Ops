"""Every Jev spend row carries a call id that is never reused (.claude/done/spm/2026-10-28-jev-spend-call-id/spec.md).

The Guardian watcher skips a mirrored legacy row only when its call id is in today's machine ledger. A row id
alone is reused after the machine ledger is reset, which let one $12 call hide another.
"""
import json
import re
import sqlite3

import pytest

from evals.jev_constitution import harness
from jev_platform import client, spend
from scripts import jev_triage as triage
from scripts import mission_control_jev_shadow as shadow
from src.tao import skill_router
from tests.jev_spend_support import BODY, QUESTION, SNAP, budget, ledger, rows, triage_ledger

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
        spend_id, spend_call_id = db.execute("SELECT spend_id, spend_call_id FROM calls WHERE id=1").fetchone()
    assert (spend_id, spend_call_id) == (machine["id"], machine["call_id"]) and HEX32.fullmatch(spend_call_id)
    assert own == spend_call_id   # the handle is the call id, never the reusable row id


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


def _collide() -> None:
    """The machine ledger is reset mid-call and a different call takes the same row id."""
    ledger().unlink()
    spend.reserve("other", 7.0)


def _assert_other_call_untouched() -> None:
    other = [r for r in rows() if r["caller"] == "other"]
    assert len(other) == 1 and (other[0]["status"], other[0]["actual_usd"]) == ("attempted", None), rows()
    notes = (ledger().parent / spend.REFUSALS).read_text().splitlines()
    assert any(json.loads(n)["kind"] == "settle_missing" for n in notes), notes


def test_settling_by_call_id_never_overwrites_a_different_call_after_a_reset():
    row, call_id = spend.reserve_call("t", 1.0)
    _collide()
    assert rows()[0]["id"] == row
    assert spend.finish(row, "answered", 0.5, 10, call_id=call_id) is False
    _assert_other_call_untouched()


def test_a_settle_that_matches_no_row_reports_it_even_without_a_call_id():
    spend.reserve("t", 1.0)
    assert spend.finish(99, "answered", 0.5, 10) is False
    assert json.loads((ledger().parent / spend.REFUSALS).read_text())["kind"] == "settle_missing"


def test_client_send_settles_its_own_call_after_a_reset():
    def post(body, timeout):
        _collide()
        return 200, {"usage": {"input_tokens": 1000}, "answers": {}}, None
    client.send(BODY, post, budget())
    _assert_other_call_untouched()


def test_harness_settles_its_own_call_after_a_reset():
    def post(body, key):
        _collide()
        return 200, {"usage": {"input_tokens": 1000}}
    harness.ask_jev(QUESTION, "state", "k", post=post)
    _assert_other_call_untouched()


def test_triage_settles_its_own_call_after_a_reset(tmp_path):
    def transport(body, key):
        _collide()
        return {"model": "jev", "answers": {}, "usage": {"input_tokens": 1000}}
    triage.evaluate(SNAP, triage_ledger(tmp_path), transport, "k")
    _assert_other_call_untouched()


def test_skill_router_default_jev_settles_its_own_call_after_a_reset(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-not-a-key")

    def evaluate(payload, key, opener=None):
        _collide()
        return {"usage": {"input_tokens": 1000}}
    monkeypatch.setattr(shadow, "evaluate", evaluate)
    skill_router.default_jev()({"q": 1})
    _assert_other_call_untouched()


def test_shadow_settles_its_own_machine_call_after_a_reset(tmp_path):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    own = shadow.reserve_call(legacy, 1000, cap=None)
    _collide()
    shadow.finish_call(legacy, own, "answered", 100)
    _assert_other_call_untouched()


def test_shadow_settles_its_own_calls_after_its_own_ledger_is_reset(tmp_path):
    """Codex round 3: only the shadow ledger is reset mid-call, so call B takes call A's local row id.
    Settling A must touch neither B's machine row nor B's shadow row."""
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    a = shadow.reserve_call(legacy, 1000, cap=None)
    legacy.unlink()
    b = shadow.reserve_call(legacy, 1000, cap=None)
    shadow.finish_call(legacy, a, "answered", 100)
    by_call = {r["call_id"]: r for r in rows()}
    assert by_call[a]["status"] == "answered" and by_call[a]["input_tokens"] == 100
    assert by_call[b]["status"] == "attempted" and by_call[b]["actual_usd"] is None
    with sqlite3.connect(legacy) as db:
        assert db.execute("SELECT status, actual_usd FROM calls WHERE spend_call_id=?", (b,)).fetchone() == ("attempted", None)


def test_a_legacy_ledger_that_already_has_spend_id_gains_spend_call_id(tmp_path):
    """The live Mini state after #955: spend_id is there, spend_call_id is not."""
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, reserved_usd REAL NOT NULL, "
                   "actual_usd REAL, input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, "
                   "spend_id INTEGER)")
    own = shadow.reserve_call(legacy, 1000, cap=None)
    with sqlite3.connect(legacy) as db:
        got = db.execute("SELECT spend_id, spend_call_id FROM calls WHERE id=1").fetchone()
    assert own == got[1] and got == (rows()[0]["id"], rows()[0]["call_id"]) and HEX32.fullmatch(got[1] or "")


class _RacedDb:
    """Another process added the column between our PRAGMA and our ALTER."""

    def __init__(self, db):
        self.db = db

    def execute(self, sql, *args):
        return iter([]) if sql.startswith("PRAGMA") else self.db.execute(sql, *args)


def test_adding_a_column_another_process_just_added_is_success():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, spend_call_id TEXT)")
    spend.add_column(_RacedDb(db), "spend_call_id", "TEXT")
    try:
        spend.add_column(_RacedDb(db), "x", "NOT A TYPE (")
    except sqlite3.OperationalError:
        return
    raise AssertionError("an ALTER that failed for another reason was swallowed")


def test_a_caller_can_give_the_machine_row_its_call_id():
    row, call_id = spend.reserve_call("t", 1.0, "f" * 32)
    assert call_id == "f" * 32 and rows()[0]["call_id"] == "f" * 32 and rows()[0]["id"] == row


def _reset_inside_the_machine_reserve(monkeypatch, legacy, outcome):
    """Codex round 4: the shadow ledger is reset after call A writes its own row and before A's machine reserve
    returns, and call B then takes A's local row id. `outcome` is what A's machine reserve does next."""
    real, seen = spend.reserve_call, {}

    def reserve(caller, usd, *call_id):
        if seen:
            return real(caller, usd, *call_id)
        seen["started"] = True
        legacy.unlink()
        seen["b"] = shadow.reserve_call(legacy, 1000, cap=None)
        return outcome(real, caller, usd, *call_id)
    monkeypatch.setattr(spend, "reserve_call", reserve)
    return seen


def _own_row(legacy, call_id):
    with sqlite3.connect(legacy) as db:
        return db.execute("SELECT id, status, actual_usd, spend_id FROM calls WHERE spend_call_id=?",
                          (call_id,)).fetchone()


def test_a_shadow_reset_inside_the_reserve_leaves_the_call_that_took_the_row_alone(tmp_path, monkeypatch, capsys):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    seen = _reset_inside_the_machine_reserve(monkeypatch, legacy, lambda real, *args: real(*args))
    a = shadow.reserve_call(legacy, 1000, cap=None)
    b = seen["b"]
    machine = {r["call_id"]: r["id"] for r in rows()}
    assert set(machine) == {a, b}
    assert _own_row(legacy, b) == (1, "attempted", None, machine[b])
    assert _own_row(legacy, a) is None and f"no row for call {a}" in capsys.readouterr().err
    shadow.finish_call(legacy, a, "answered", 100)
    assert _own_row(legacy, b) == (1, "attempted", None, machine[b])


def test_a_refused_call_after_a_shadow_reset_leaves_the_call_that_took_the_row_alone(tmp_path, monkeypatch):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"

    def refuse(real, *args):
        raise spend.SpendCapReached("cap")
    seen = _reset_inside_the_machine_reserve(monkeypatch, legacy, refuse)
    assert shadow.reserve_call(legacy, 1000, cap=None) is None
    assert _own_row(legacy, seen["b"])[:3] == (1, "attempted", None)


def test_the_own_ledger_holds_each_call_id_once(tmp_path):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    a = shadow.reserve_call(legacy, 1000, cap=None)
    with sqlite3.connect(legacy) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO calls(day, reserved_usd, status, created_at, spend_call_id) "
                   "VALUES ('d', 0, 'x', 'c', ?)", (a,))
