"""A refused Jev call (HTTP 401/403) stops a batch at the first refusal and is ledgered as "refused", reserve kept. Offline fakes only."""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

from jev_platform import client
from tests.jev_spend_support import BODY, PRICE, budget, rows, watcher_sum, today

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)

SNAPS = [{"run_id": f"r{i}", "sha": "abc", "surface": f"/s{i}", "contract": "J1", "page_text": "hello",
          "network": []} for i in range(3)]


def _refuse(code):
    calls = []

    def post(body, timeout):
        calls.append(1)
        return code, None, None
    return post, calls


def _http_error(code):
    calls = []

    def transport(body, key):
        calls.append(1)
        raise urllib.error.HTTPError("https://x", code, "refused", {}, None)
    return transport, calls


@pytest.mark.parametrize("code", [401, 403])
def test_triage_run_stops_at_the_first_refused_snapshot(tmp_path, code):
    transport, calls = _http_error(code)
    out = tmp_path / "labels.jsonl"
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-10-28")
    n = jt.run(SNAPS, out, ledger, transport, "k")
    assert len(calls) == 1 and n == 1
    assert json.loads(out.read_text().splitlines()[0])["status"] == "AUTH_REFUSED"


@pytest.mark.parametrize("code", [401, 403])
def test_triage_refusal_is_ledgered_refused_with_the_reserve_kept(tmp_path, code):
    transport, _ = _http_error(code)
    jt.run(SNAPS, tmp_path / "l.jsonl", jt.Ledger(tmp_path / "s.json", "2026-10-28"), transport, "k")
    (row,) = rows()
    assert row["status"] == "refused" and row["actual_usd"] is None
    assert watcher_sum(today()) == pytest.approx(row["reserved_usd"]) and row["reserved_usd"] > 0


def test_triage_a_500_does_not_stop_the_run(tmp_path):
    transport, calls = _http_error(500)
    n = jt.run(SNAPS, tmp_path / "l.jsonl", jt.Ledger(tmp_path / "s.json", "2026-10-28"), transport, "k")
    assert n == 3 and len(calls) == 3


@pytest.mark.parametrize("code", [401, 403])
def test_client_send_refusal_is_status_refused_not_retried_reserve_kept(code):
    post, calls = _refuse(code)
    assert client.send(BODY, post, budget()) == {"error": f"signal_unavailable:http_{code}"}
    (row,) = rows()
    assert len(calls) == 1 and row["status"] == "refused" and row["actual_usd"] is None
    assert watcher_sum(today()) == pytest.approx(client.RESERVE_USD)


def test_client_send_500_keeps_the_conservative_reserve():
    post, _ = _refuse(500)
    client.send(BODY, post, budget())
    (row,) = rows()
    assert row["status"] == "error" and row["actual_usd"] is None
    assert watcher_sum(today()) == pytest.approx(client.RESERVE_USD)


def test_budget_keeps_the_reserve_after_a_refusal_and_buys_no_attempts():
    b = budget()
    fixed = b.max_attempts
    post, _ = _refuse(401)
    client.send(BODY, post, b)
    assert b.spent == pytest.approx(client.RESERVE_USD) and b.actual == 0.0
    assert b.attempts == 1 and b.max_attempts == fixed


def test_budget_keeps_the_reserve_after_a_500():
    b = budget()
    post, _ = _refuse(500)
    client.send(BODY, post, b)
    assert b.spent == pytest.approx(client.RESERVE_USD)


@pytest.mark.parametrize("code", [401, 403])
def test_a_shared_budget_sends_nothing_after_a_refusal(code):
    b = budget()
    post, calls = _refuse(code)
    for _ in range(3):
        out = client.send(BODY, post, b)
    assert len(calls) == 1 and out["error"].startswith("signal_unavailable:http_")


@pytest.mark.parametrize("code", [401, 403])
def test_scout_batch_of_two_files_sends_one_request_on_a_refusal(tmp_path, code):
    from jev_scale_support import GOOD, make_repo
    from jev_platform import scout

    repo = make_repo(tmp_path, {"src/domain/a.ts": GOOD, "src/domain/b.ts": GOOD})
    calls = []

    def post(body, timeout):
        calls.append(1)
        return code, None, None

    out = scout.scout_files(repo, ["src/domain/*"], ["known-issue"], post, budget())
    assert len(calls) == 1 and len(out["results"]) == 1
    assert out["results"][0]["unavailable"] == f"signal_unavailable:http_{code}"
    assert out["skipped"] == [{"path": "src/domain/b.ts", "reason": "key refused"}]
    assert out["reserved_usd"] == pytest.approx(client.RESERVE_USD) and out["actual_usd"] == 0.0
    assert "spent_usd" not in out


def test_scout_reports_actual_spend_separately_from_the_reserve(tmp_path):
    from jev_scale_support import GOOD, make_repo
    from jev_platform import scout

    repo = make_repo(tmp_path, {"src/domain/a.ts": GOOD})
    post = lambda body, timeout: (200, {"usage": {"input_tokens": 1000}, "answers": {}}, None)  # noqa: E731
    out = scout.scout_files(repo, ["src/domain/*"], ["known-issue"], post, budget())
    assert out["actual_usd"] == pytest.approx(1000 * PRICE) and out["reserved_usd"] == pytest.approx(1000 * PRICE)


# ---- the race: a refusal must stop calls already past the halted check (concurrent workers, one Budget) ----

def _race_pair(monkeypatch, send_one, gate_seed=None):
    """Worker 'second' is held inside spend.reserve_call until worker 'first' has been refused; then it is released."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from jev_platform import spend

    original, local = spend.reserve_call, threading.local()
    second_in_reserve, first_done, release = threading.Event(), threading.Event(), threading.Event()

    def reserve_call(caller, amount, call_id=None):
        if getattr(local, "name", "") == "second":
            second_in_reserve.set()
            assert release.wait(5)
        return original(caller, amount, call_id)

    monkeypatch.setattr(spend, "reserve_call", reserve_call)

    def call(name):
        local.name = name
        if name == "first":
            assert second_in_reserve.wait(5)
        out = send_one(name)
        if name == "first":
            first_done.set()
            release.set()
        return out

    with ThreadPoolExecutor(max_workers=2) as pool:
        f, s = pool.submit(call, "first"), pool.submit(call, "second")
        return f.result(10), s.result(10)


@pytest.mark.parametrize("code", [401, 403])
def test_a_worker_blocked_in_reserve_does_not_send_after_another_is_refused(monkeypatch, code):
    b = budget()
    assert "data" in client.send(BODY, lambda body, t: (200, {"usage": {"input_tokens": 1}, "answers": {}}, None), b)
    sent = []

    def post(body, timeout):
        sent.append(body["state"])
        return code, None, None

    first, second = _race_pair(monkeypatch, lambda name: client.send({**BODY, "state": name}, post, b))
    assert sent == ["first"]
    assert first == second == {"error": f"signal_unavailable:http_{code}"}
    by_status = {r["status"]: r for r in rows()}
    assert by_status["not_sent"]["actual_usd"] == 0.0 and by_status["refused"]["actual_usd"] is None


@pytest.mark.parametrize("code", [401, 403])
def test_eight_workers_on_one_budget_send_exactly_one_request_with_a_bad_key(code):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    b, sent, start = budget(), [], threading.Barrier(8)

    def post(body, timeout):
        sent.append(1)
        time.sleep(0.2)  # long enough for every other worker to be past the halted check
        return code, None, None

    def work(i):
        start.wait(5)
        return client.send({**BODY, "state": str(i)}, post, b)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outs = list(pool.map(work, range(8)))
    assert len(sent) == 1 and {o["error"] for o in outs} == {f"signal_unavailable:http_{code}"}


def test_the_gate_opens_after_one_non_auth_response_so_workers_run_in_parallel():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    b, inside, peak, lock = budget(), [0], [0], threading.Lock()
    both = threading.Barrier(2)

    def post(body, timeout):
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        try:
            if body["state"] != "canary":
                both.wait(5)  # only passes if two requests are in flight at once
        finally:
            with lock:
                inside[0] -= 1
        return 500, None, None

    client.send({**BODY, "state": "canary"}, post, b)  # a 500 is a response: the key is not refused
    with ThreadPoolExecutor(max_workers=2) as pool:
        outs = list(pool.map(lambda n: client.send({**BODY, "state": n}, post, b), ["a", "b"]))
    assert peak[0] == 2 and all(o["error"] == "signal_unavailable:http_500" for o in outs)


def test_skill_routing_eval_stops_at_the_first_refused_batch(tmp_path):
    from types import SimpleNamespace
    from urllib.error import HTTPError

    from evals.skill_routing import run as sr_run

    calls = []

    def refuse(batch, key):
        calls.append(1)
        raise HTTPError("https://x", 401, "refused", {}, None)

    big = "x" * (sr_run.CALL_TOKENS * 4 + 10)  # one case per Jev call
    cases = [{"text": big, "split": "tune"} for _ in range(3)]
    cat = [SimpleNamespace(name="a", description="d")]
    args = SimpleNamespace(ledger=tmp_path / "l.sqlite", cap_usd=5.0, k=1, min_confidence=0.0, budget=1)
    sr_run.jev_batch, orig_batch = refuse, sr_run.jev_batch
    orig_short, sr_run.sr.shortlist = sr_run.sr.shortlist, lambda text, cat, k: [("a", 1.0)]
    try:
        with pytest.raises(SystemExit):
            sr_run.jev_rows(cases, cat, {}, args, "k")
    finally:
        sr_run.jev_batch, sr_run.sr.shortlist = orig_batch, orig_short
    assert len(calls) == 1
