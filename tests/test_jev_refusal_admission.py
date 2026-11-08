"""No request is admitted after a refusal is published; the refusal is published before any ledger I/O.

Contract (jev_platform.client.AuthGate): before one non-401/403 response has been seen, exactly one request is
ever sent. After it, requests admitted before a refusal is published may still finish (at most workers-1);
none is admitted after. Fake transports only.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from evals.jev_constitution import harness as h
from jev_platform import client, spend
from tests.jev_spend_support import BODY, budget, rows, watcher_sum, today

Q = {"id": "t-01", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no"}
OK = lambda body, t: (200, {"usage": {"input_tokens": 1}, "answers": {}}, None)  # noqa: E731


def _open_client_gate():
    b = budget()
    assert "data" in client.send(BODY, OK, b)
    return b


def _open_harness_gate():
    g = client.AuthGate()
    g.answered()
    return g


def _stall_refused_settlement(monkeypatch):
    """spend.finish(.., 'refused') blocks on an Event; returns (entered, release)."""
    entered, release, original = threading.Event(), threading.Event(), spend.finish

    def finish(row, status, *a, **kw):
        if status == "refused":
            entered.set()
            assert release.wait(5)
        return original(row, status, *a, **kw)

    monkeypatch.setattr(spend, "finish", finish)
    return entered, release


@pytest.mark.parametrize("code", [401, 403])
def test_client_a_new_worker_started_during_refusal_settlement_is_not_sent(monkeypatch, code):
    b = _open_client_gate()
    entered, release = _stall_refused_settlement(monkeypatch)
    second_calls = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.send, BODY, lambda body, t: (code, None, None), b)
        assert entered.wait(5)
        out = client.send(BODY, lambda body, t: second_calls.append(1) or (500, None, None), b)
        release.set()
        first.result(5)
    assert second_calls == [] and out == {"error": f"signal_unavailable:http_{code}"}
    assert [r["status"] for r in rows()] == ["answered", "refused"]  # the late worker reserved nothing


@pytest.mark.parametrize("code", [401, 403])
def test_harness_a_new_worker_started_during_refusal_settlement_is_not_sent(monkeypatch, code):
    g = _open_harness_gate()
    entered, release = _stall_refused_settlement(monkeypatch)
    second_calls = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(h.ask_jev, Q, "a", "k", lambda body, key: (code, "refused"), g)
        assert entered.wait(5)
        out = h.ask_jev(Q, "b", "k", lambda body, key: second_calls.append(1) or (500, "x"), g)
        release.set()
        first.result(5)
    assert second_calls == [] and out[0] == 0
    assert [r["status"] for r in rows()] == ["refused"]  # the late worker reserved nothing


@pytest.mark.parametrize("code", [401, 403])
def test_a_refusal_while_workers_are_in_flight_admits_nobody_afterwards(code):
    n = 6
    b = _open_client_gate()
    in_flight, calls, lock = threading.Barrier(n), [], threading.Lock()

    def post(body, timeout):
        with lock:
            calls.append(body["state"])
        in_flight.wait(5)  # all n are admitted and inside the transport together
        return (code, None, None) if body["state"] == "0" else (500, None, None)

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(lambda i: client.send({**BODY, "state": str(i)}, post, b), range(n)))
    admitted_before = b.admitted
    later = [client.send({**BODY, "state": f"late{i}"}, post, b) for i in range(4)]
    assert len(calls) == n and b.admitted == admitted_before
    assert all(o == {"error": f"signal_unavailable:http_{code}"} for o in later)


def test_client_an_exception_in_the_refusal_path_still_publishes_it_and_releases_the_lock(monkeypatch):
    b = budget()  # canary phase: the dispatch lock is held across the request
    monkeypatch.setattr(spend, "finish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ledger down")))
    with pytest.raises(RuntimeError):
        client.send(BODY, lambda body, t: (401, None, None), b)
    assert b.halted == "signal_unavailable:http_401"
    assert b._canary.acquire(blocking=False)


def test_harness_an_exception_in_the_refusal_path_still_publishes_it_and_releases_the_lock(monkeypatch):
    g = client.AuthGate()
    monkeypatch.setattr(spend, "finish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ledger down")))
    with pytest.raises(RuntimeError):
        h.ask_jev(Q, "a", "k", lambda body, key: (401, "refused"), g)
    assert g.halted == "signal_unavailable:http_401"
    assert g._canary.acquire(blocking=False)


# ---- the default cap must hold for the triage caller: it reserves the maximum, not an estimate ----

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)
SNAP = {"run_id": "r1", "sha": "abc", "surface": "/x", "contract": "J1", "page_text": "hello", "network": []}


def _estimate(snap):
    body = jt.build_body(snap)
    return jt.estimate_tokens(body["state"] + json.dumps(body["questions"])) * jt.PRICE_PER_MTOK_INPUT / 1e6


@pytest.mark.parametrize("headroom", [0.0002, 0.0005])
def test_triage_is_refused_at_reserve_time_when_the_maximum_charge_would_pass_the_cap(tmp_path, headroom):
    spend.reserve("prior", 20.0 - headroom)  # JEV_DAILY_CAP_USD unset: the $20 default
    calls = []

    def transport(body, key):
        calls.append(1)
        return {"model": "m", "usage": {"input_tokens": 64000}, "answers": {}}

    row = jt.evaluate(SNAP, jt.Ledger(tmp_path / "s.json", "2026-10-28"), transport, "k")
    assert row["status"] == "SPEND_CAP" and calls == []
    assert watcher_sum(today()) <= 20.0


def test_triage_one_token_over_the_estimate_cannot_pass_the_cap(tmp_path):
    spend.reserve("prior", 20.0 - _estimate(SNAP))
    n = round(_estimate(SNAP) / (jt.PRICE_PER_MTOK_INPUT / 1e6)) + 1
    row = jt.evaluate(SNAP, jt.Ledger(tmp_path / "s.json", "2026-10-28"),
                      lambda b, k: {"model": "m", "usage": {"input_tokens": n}, "answers": {}}, "k")
    assert row["status"] == "SPEND_CAP" and watcher_sum(today()) <= 20.0


@pytest.mark.parametrize("used", [64000, 999999])
def test_triage_a_call_that_fits_never_settles_above_its_reserve(tmp_path, used):
    spend.reserve("prior", 19.99)
    jt.evaluate(SNAP, jt.Ledger(tmp_path / "s.json", "2026-10-28"),
                lambda b, k: {"model": "m", "usage": {"input_tokens": used}, "answers": {}}, "k")
    assert watcher_sum(today()) <= 20.0
