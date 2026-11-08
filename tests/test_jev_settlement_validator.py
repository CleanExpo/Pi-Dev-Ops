"""Every writer of actual_usd goes through one validator: usage must be a non-bool int in [0, 64000].

Missing, negative, oversized or mistyped usage -> actual NULL, input_tokens NULL, reserve kept: the day's total can
never be lowered by a bad reply nor pushed past what was reserved. Fake transports only."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.jev_constitution import harness as h
from jev_platform import client, spend
from scripts import mission_control_jev_shadow as shadow
from tests.jev_spend_support import BODY, budget, rows, today, watcher_sum

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)
Q = {"id": "t-01", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no"}
SNAP = {"run_id": "r1", "sha": "abc", "surface": "/x", "contract": "J1", "page_text": "hello", "network": []}
BAD = [("oversized", {"input_tokens": 640000}), ("negative", {"input_tokens": -64000}), ("missing", {}),
       ("bool", {"input_tokens": True}), ("string", {"input_tokens": "5"}), ("float", {"input_tokens": 1.5}),
       ("no_usage_key", None),
       # review r6 (0bee5cb0): usage that is not an object crashed the skill-routing eval after its reserved call
       ("usage_list", [1]), ("usage_string", "5"), ("usage_number", 5)]


def _usage_body(usage):
    return {"model": "m", "answers": {}, **({} if usage is None else {"usage": usage})}


def _client(usage, tmp):
    client.send(BODY, lambda b, t: (200, _usage_body(usage), None), budget())


def _harness(usage, tmp):
    resp = {"answers": {"q": {"type": "noul", "noul": 1.0}}, **({} if usage is None else {"usage": usage})}
    h.ask_jev(Q, "s", "k", lambda b, k: (200, resp), client.AuthGate())


def _triage(usage, tmp):
    jt.evaluate(SNAP, jt.Ledger(tmp / "x.json", "2026-10-28"), lambda b, k: _usage_body(usage), "k")


def _shadow_finish(usage, tmp):
    own = tmp / "own.sqlite"
    call_id = shadow.reserve_call(own, shadow.RESERVED_INPUT_TOKENS_PER_CALL)
    shadow.finish_call(own, call_id, "answered", usage.get("input_tokens") if isinstance(usage, dict) else None)
    with sqlite3.connect(own) as db:
        assert db.execute("SELECT actual_usd, input_tokens FROM calls").fetchone() == (None, None)


def _skill_routing_eval(usage, tmp):
    from evals.skill_routing import run as sr_run

    args = SimpleNamespace(k=1, ledger=tmp / "own.sqlite", cap_usd=None)
    fake = {"result": _usage_body(usage), "questions": {}}
    sr_run.jev_batch, orig = (lambda batch, key: fake), sr_run.jev_batch
    short, sr_run.sr.shortlist = sr_run.sr.shortlist, lambda text, cat, k: [("x", 1)]
    packed, sr_run.packed = sr_run.packed, lambda pending, names: [(pending, 1)]
    rowsfn, sr_run.chunk_rows = sr_run.chunk_rows, lambda *a, **k: []
    try:
        sr_run.jev_rows([{"text": "t", "expected": "x"}], [SimpleNamespace(name="x", description="d")], {}, args, "k")
    finally:
        sr_run.jev_batch, sr_run.sr.shortlist, sr_run.packed, sr_run.chunk_rows = orig, short, packed, rowsfn


WRITERS = {"client.send": _client, "harness.ask_jev": _harness, "triage.evaluate": _triage,
           "skill_routing_eval": _skill_routing_eval}


@pytest.mark.parametrize("writer", WRITERS)
@pytest.mark.parametrize("name, usage", BAD)
def test_invalid_usage_keeps_the_reserve_and_never_settles_actual(writer, name, usage, tmp_path):
    prior = 20.0 - client.RESERVE_USD  # exactly one maximum reserve of headroom under the $20 default
    spend.reserve("prior", prior)
    WRITERS[writer](usage, tmp_path)
    row = [r for r in rows() if r["caller"] != "prior"][0]
    assert row["actual_usd"] is None and row["input_tokens"] is None
    assert watcher_sum(today()) == pytest.approx(prior + row["reserved_usd"]) and watcher_sum(today()) <= 20.0 + 1e-9
    with pytest.raises(spend.SpendCapReached):  # the lie did not lower the total: nothing more is admitted
        spend.reserve("next", client.RESERVE_USD)


@pytest.mark.parametrize("result", [[1], "text", None, {"model": "m", "answers": [1], "usage": {"input_tokens": 10}}])
def test_skill_routing_eval_settles_a_malformed_reply(result, tmp_path):
    """A reply whose result (or its answers) is not an object is settled, keeps its reserve, and is scored as
    malformed: the eval never crashes between a reserved call and its settlement. The real chunk_rows runs."""
    from evals.skill_routing import run as sr_run

    args = SimpleNamespace(k=1, ledger=tmp_path / "own.sqlite", cap_usd=None, budget=10_000, min_confidence=0.0)
    fake = {"result": result, "questions": {"q0": {"type": "choice", "criteria": {"x": "d"}}}}
    sr_run.jev_batch, orig = (lambda batch, key: fake), sr_run.jev_batch
    short, sr_run.sr.shortlist = sr_run.sr.shortlist, lambda text, cat, k: [("x", 1)]
    packed, sr_run.packed = sr_run.packed, lambda pending, names: [(pending, 1)]
    try:
        out, cost = sr_run.jev_rows([{"text": "t", "expected": "x"}], [SimpleNamespace(name="x", description="d")], {}, args, "k")
    finally:
        sr_run.jev_batch, sr_run.sr.shortlist, sr_run.packed = orig, short, packed
    assert [r["picked"] for r in out] == [["<malformed>"]] and cost["errors"] == 1
    row = rows()[0]
    assert row["status"] == "answered" and row["reserved_usd"] > 0
    assert row["actual_usd"] == (None if not isinstance(result, dict) else pytest.approx(10 * spend.USD_PER_TOKEN))


@pytest.mark.parametrize("name, usage", BAD)
def test_shadow_finish_call_validates_its_input(name, usage, tmp_path):
    _shadow_finish(usage, tmp_path)


@pytest.mark.parametrize("writer", WRITERS)
def test_valid_usage_is_the_positive_control(writer, tmp_path):
    prior = 20.0 - client.RESERVE_USD
    spend.reserve("prior", prior)
    WRITERS[writer]({"input_tokens": 64000}, tmp_path)
    row = [r for r in rows() if r["caller"] != "prior"][0]
    assert row["input_tokens"] == 64000 and row["actual_usd"] == pytest.approx(client.RESERVE_USD)
    assert watcher_sum(today()) <= 20.0 + 1e-9


def test_the_validator_itself():
    assert [spend.valid_tokens(v) for v in (0, 64000, 64001, -1, True, 1.0, "1", None)] == [0, 64000, None, None, None, None, None, None]


def _aux(tmp):
    return json.loads((tmp / "aux.json").read_text())["2026-10-28"]


@pytest.mark.parametrize("name, usage", BAD)
def test_triage_side_ledger_never_counts_less_than_the_reserve(name, usage, tmp_path):
    jt.evaluate(SNAP, jt.Ledger(tmp_path / "aux.json", "2026-10-28"), lambda b, k: _usage_body(usage), "k")
    assert _aux(tmp_path) == pytest.approx(round(client.RESERVE_USD, 6))


@pytest.mark.parametrize("exc", [urllib.error.HTTPError("u", 401, "x", None, None), TimeoutError("t")])
def test_triage_side_ledger_keeps_the_reserve_on_refusal_and_error(exc, tmp_path):
    def transport(body, key):
        raise exc
    jt.evaluate(SNAP, jt.Ledger(tmp_path / "aux.json", "2026-10-28"), transport, "k")
    assert _aux(tmp_path) == pytest.approx(round(client.RESERVE_USD, 6))


def test_triage_side_ledger_positive_control(tmp_path):
    jt.evaluate(SNAP, jt.Ledger(tmp_path / "aux.json", "2026-10-28"), lambda b, k: _usage_body({"input_tokens": 1000}), "k")
    row = rows()[0]
    assert _aux(tmp_path) == pytest.approx(round(row["actual_usd"], 6)) and row["input_tokens"] == 1000


CONTROL_ARGS = SimpleNamespace(question="no-such-question", limit=None, workers=1)


def test_harness_control_request_is_refused_when_the_cap_is_full():
    spend.reserve("prior", 20.0)
    sent = []
    code = h.run(CONTROL_ARGS, env={"TYPESAFE_API_KEY": "k"}, post=lambda b, k: sent.append(b) or (401, "x"))
    assert sent == [] and code == h.EXIT_BLOCKED


def test_harness_control_request_is_reserved_and_settled_as_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "RESULTS", tmp_path / "results")  # the run writes a report; never into the repo
    sent = []
    h.run(CONTROL_ARGS, env={"TYPESAFE_API_KEY": "k"}, post=lambda b, k: sent.append(b) or (401, "x"))
    assert len(sent) == 1
    row = [r for r in rows() if r["caller"] == h.CALLER][0]
    assert row["status"] == "refused" and row["actual_usd"] is None
    assert row["reserved_usd"] == pytest.approx(client.RESERVE_USD)
