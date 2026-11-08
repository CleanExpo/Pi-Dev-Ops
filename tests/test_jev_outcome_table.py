"""Table-driven: every transport outcome x every Jev dispatcher (the transition table in jev_platform/auth_gate.py).

Gated, parallel-capable dispatchers (client.send, the constitution harness): a real HTTP status proves the key and
opens the gate; 401/403 halt it; NO HTTP response (status 0, None, an exception) leaves it closed, so the next
request is still the lone canary. Sequential dispatchers (triage, shadow main, skill-routing eval) stop at the
first 401/403 and carry on through every other outcome. Fake transports only.
"""
from __future__ import annotations

import functools
import importlib.util
import json
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.jev_constitution import harness as h
from jev_platform import client
from tests.jev_spend_support import BODY, budget

Q = {"id": "t-01", "question": "Does it comply?", "criteria_true": "yes", "criteria_false": "no"}
URL_ERROR = urllib.error.URLError("no route")
# (name, transport behaviour, key proven?)  behaviour: int status, None, or an exception to raise
OUTCOMES = [("200", 200, True), ("302", 302, True), ("404", 404, True), ("429", 429, True), ("500", 500, True),
            ("status0", 0, False), ("status_none", None, False), ("urlerror", URL_ERROR, False),
            ("timeout", TimeoutError("slow"), False)]


def _reply(behaviour):
    if isinstance(behaviour, BaseException):
        raise behaviour
    return behaviour


def gated_client(behaviour_for):
    gate, calls = budget(), []

    def call(state):
        def post(body, timeout):
            calls.append(state)
            time.sleep(0.15)
            return _reply(behaviour_for(state)), None, None
        try:
            return client.send({**BODY, "state": state}, post, gate)
        except Exception as exc:  # noqa: BLE001
            return exc
    return gate, calls, call


def gated_harness(behaviour_for):
    gate, calls = client.AuthGate(), []

    def call(state):
        def post(body, key):
            calls.append(state)
            time.sleep(0.15)
            return _reply(behaviour_for(state)), {}
        try:
            return h.ask_jev(Q, state, "k", post, gate=gate)
        except Exception as exc:  # noqa: BLE001
            return exc
    return gate, calls, call


DISPATCHERS = {"client.send": gated_client, "harness.ask_jev": gated_harness}


def _batch(call, n=8):
    start = threading.Barrier(n)

    def work(i):
        start.wait(5)
        return call(f"b{i}")
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(work, range(n)))


@pytest.mark.parametrize("dispatcher", DISPATCHERS)
@pytest.mark.parametrize("name, behaviour, proven", OUTCOMES)
def test_outcome_opens_the_gate_only_when_a_real_http_response_proved_the_key(dispatcher, name, behaviour, proven):
    gate, calls, call = DISPATCHERS[dispatcher](lambda s: behaviour if s == "first" else 401)
    call("first")
    assert gate.canary_done is proven and gate.halted is None
    _batch(call)  # a bad key from here on
    if proven:
        assert len(calls) >= 2 and gate.halted
    else:
        assert len(calls) == 2  # the first request, then exactly ONE more: the canary
        assert gate.halted


@pytest.mark.parametrize("dispatcher", DISPATCHERS)
@pytest.mark.parametrize("code", [401, 403])
def test_a_refusal_halts_and_nothing_further_is_sent(dispatcher, code):
    gate, calls, call = DISPATCHERS[dispatcher](lambda s: code)
    call("first")
    assert gate.halted and not gate.canary_done
    _batch(call)
    assert calls == ["first"]


# ---- sequential dispatchers: stop at the first 401/403, carry on through everything else ----

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)
SNAPS = [{"run_id": f"r{i}", "sha": "abc", "surface": f"/s{i}", "contract": "J1", "page_text": "hello",
          "network": []} for i in range(3)]
SEQ = [("401", 401, 1), ("403", 403, 1), ("404", 404, 3), ("429", 429, 3), ("500", 500, 3), ("urlerror", None, 3)]


def _http_error(code):
    return URL_ERROR if code is None else urllib.error.HTTPError("https://x", code, "x", {}, None)


@pytest.mark.parametrize("name, code, expected_calls", SEQ)
def test_triage_run(tmp_path, name, code, expected_calls):
    calls = []

    def transport(body, key):
        calls.append(1)
        raise _http_error(code)
    jt.run(SNAPS, tmp_path / "l.jsonl", jt.Ledger(tmp_path / "s.json", "2026-10-28"), transport, "k")
    assert len(calls) == expected_calls


@pytest.mark.parametrize("name, code, expected_calls", SEQ)
def test_shadow_main(tmp_path, monkeypatch, name, code, expected_calls):
    from scripts import mission_control_jev_shadow as shadow

    calls = []

    def opener(req, timeout):
        calls.append(1)
        raise _http_error(code)
    monkeypatch.setattr(shadow, "run_line", functools.partial(shadow.run_line, opener=opener))
    monkeypatch.setenv("TYPESAFE_API_KEY", "synthetic-key")
    snap = {"run_id": "r", "sha": "ded1a54e24f547861c89e85c5056e8b77176bb59", "surface": "/c", "visible_text": "t",
            "data_classification": "synthetic"}
    source = tmp_path / "in.jsonl"
    source.write_text("".join(json.dumps(snap) + "\n" for _ in range(3)))
    shadow.main([str(source), str(tmp_path / "out.jsonl"), "--live-synthetic", "--ledger", str(tmp_path / "b.sqlite")])
    assert len(calls) == expected_calls


@pytest.mark.parametrize("name, code, expected_calls", SEQ)
def test_skill_routing_eval(tmp_path, monkeypatch, name, code, expected_calls):
    from evals.skill_routing import run as sr_run

    calls = []

    def jev_batch(batch, key):
        calls.append(1)
        raise _http_error(code)
    monkeypatch.setattr(sr_run, "jev_batch", jev_batch)
    monkeypatch.setattr(sr_run.sr, "shortlist", lambda text, cat, k: [("a", 1.0)])
    big = "x" * (sr_run.CALL_TOKENS * 4 + 10)  # one case per Jev call
    args = SimpleNamespace(ledger=tmp_path / "l.sqlite", cap_usd=None, k=1, min_confidence=0.0, budget=1)
    try:
        sr_run.jev_rows([{"text": big, "split": "tune"}] * 3, [SimpleNamespace(name="a", description="d")], {}, args, "k")
    except SystemExit:
        pass
    assert len(calls) == expected_calls
