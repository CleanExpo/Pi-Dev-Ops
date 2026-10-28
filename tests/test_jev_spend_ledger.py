"""The machine Jev spend ledger (.claude/done/spm/2026-10-28-jev-spend-ledger/spec.md, C1).

Every fake transport here checks, from inside the call, that the spend row already exists: order is the
property under test, and a count taken after the call cannot see it. No network, no key."""
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evals.jev_constitution import harness
from jev_platform import client, spend
from scripts import jev_triage as triage
from scripts import mission_control_jev_shadow as shadow
from src.tao import skill_router
from tests.jev_spend_support import (BODY, PRICE, QUESTION, ROOT, SHADOW_SNAP, SNAP, budget, ledger, rows, shadow_reply,
                                     today, triage_ledger, unwritable, watcher_sum)


def test_default_path_is_absolute_under_home_and_resolved_per_call(tmp_path, monkeypatch):
    assert ledger().parent == tmp_path  # the conftest isolation fixture, never the real ledger
    assert spend.ledger_path() != Path(os.path.expanduser(spend.DEFAULT))
    monkeypatch.delenv("JEV_SPEND_LEDGER")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert spend.ledger_path() == tmp_path / "home" / ".local" / "state" / "jev" / "spend.sqlite"
    monkeypatch.setenv("JEV_SPEND_LEDGER", str(tmp_path / "later.sqlite"))
    assert spend.ledger_path() == tmp_path / "later.sqlite"


def test_reserve_writes_to_the_path_set_after_import(tmp_path, monkeypatch):
    target = tmp_path / "set-after-import.sqlite"
    monkeypatch.setenv("JEV_SPEND_LEDGER", str(target))
    spend.reserve("t", 0.5)
    assert [r["reserved_usd"] for r in rows(target)] == [0.5]


@pytest.mark.parametrize("value", ["", "   ", "relative/spend.sqlite"])
def test_bad_paths_are_refused_not_resolved_against_cwd(monkeypatch, value, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JEV_SPEND_LEDGER", value)
    with pytest.raises(spend.SpendUnrecorded):
        spend.reserve("t", 0.1)
    assert not (tmp_path / "relative").exists()


def test_directory_path_is_refused_and_the_refusal_is_noted(tmp_path, monkeypatch):
    folder = tmp_path / "a-dir"
    folder.mkdir()
    monkeypatch.setenv("JEV_SPEND_LEDGER", str(folder))
    with pytest.raises(spend.SpendUnrecorded):
        spend.reserve("caller-x", 0.1)
    lines = [json.loads(line) for line in (tmp_path / spend.REFUSALS).read_text().splitlines()]
    assert lines[-1]["kind"] == "reserve_failed" and lines[-1]["caller"] == "caller-x"
    assert "state" not in json.dumps(lines[-1])  # amounts, names and classes only


@pytest.fixture
def brisbane(monkeypatch):
    monkeypatch.setenv("TZ", "Australia/Brisbane")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_day_is_the_utc_date_even_when_local_date_differs(brisbane, monkeypatch):
    stamp = datetime(2026, 10, 27, 15, 0, tzinfo=UTC).timestamp()  # 01:00 on 28/10 in Brisbane
    monkeypatch.setattr(spend, "_now", lambda: stamp)
    spend.reserve("t", 0.25)
    (row,) = rows()
    assert row["day"] == "2026-10-27"
    assert row["created_at"].startswith("2026-10-27T15:00:00")


def test_watcher_sql_splits_days_at_utc_midnight(monkeypatch):
    late = datetime(2026, 10, 27, 23, 59, 59, tzinfo=UTC).timestamp()
    monkeypatch.setattr(spend, "_now", lambda: late)
    spend.reserve("t", 0.4)
    assert watcher_sum("2026-10-27") == pytest.approx(0.4)
    assert watcher_sum("2026-10-28") == 0


def test_client_send_records_before_the_request_and_settles_after():
    seen = []

    def post(body, timeout):
        seen.append([r["status"] for r in rows()])
        return 200, {"usage": {"input_tokens": 1000}, "answers": {}}, None

    out = client.send(BODY, post, budget())
    assert "data" in out
    assert seen == [["attempted"]]
    (row,) = rows()
    assert row["caller"] == "jev_platform" and row["status"] == "answered"
    assert row["actual_usd"] == pytest.approx(1000 * PRICE) and row["input_tokens"] == 1000
    assert row["reserved_usd"] == pytest.approx(client.RESERVE_USD)


def test_client_send_records_one_row_per_attempt_including_a_429_retry():
    calls = []

    def post(body, timeout):
        calls.append(len(rows()))
        if len(calls) == 1:
            return 429, None, 0
        return 200, {"usage": {"input_tokens": 10}, "answers": {}}, None

    assert "data" in client.send(BODY, post, budget(), sleep=lambda s: None)
    assert calls == [1, 2]
    assert [r["status"] for r in rows()] == ["error", "answered"]


def test_client_send_keeps_the_reserve_when_usage_is_missing_or_the_transport_fails():
    client.send(BODY, lambda b, t: (200, {"answers": {}}, None), budget())

    def boom(body, timeout):
        raise OSError("network down")

    assert client.send(BODY, boom, budget()) == {"error": "signal_unavailable:transport"}
    first, second = rows()
    assert first["actual_usd"] is None and second["status"] == "error" and second["actual_usd"] is None
    assert watcher_sum(today()) == pytest.approx(2 * client.RESERVE_USD)


def test_watcher_sql_sums_a_ledger_written_through_client_send():
    client.send(BODY, lambda b, t: (200, {"usage": {"input_tokens": 1000}, "answers": {}}, None), budget())
    client.send(BODY, lambda b, t: (200, {"answers": {}}, None), budget())
    assert watcher_sum(today()) == pytest.approx(1000 * PRICE + client.RESERVE_USD)


def test_settle_failure_after_a_paid_reply_returns_the_reply_once_and_never_retries():
    posts = []

    def post(body, timeout):
        posts.append(1)
        path = ledger()
        path.unlink()
        path.mkdir()  # the ledger is now unwritable for the settle
        return 200, {"usage": {"input_tokens": 5}, "answers": {"q": 1}}, None

    out = client.send(BODY, post, budget())
    assert out == {"data": {"usage": {"input_tokens": 5}, "answers": {"q": 1}}}
    assert posts == [1]
    lines = (ledger().parent / spend.REFUSALS).read_text().splitlines()
    assert json.loads(lines[-1])["kind"] == "settle_failed"


def test_client_send_sends_nothing_when_the_ledger_is_unwritable(tmp_path, monkeypatch):
    unwritable(tmp_path, monkeypatch)
    posts = []
    out = client.send(BODY, lambda b, t: posts.append(1) or (200, {}, None), budget())
    assert out == {"error": "spend_unrecorded"}
    assert posts == []


def test_harness_records_before_the_request():
    seen = []

    def post(body, key):
        seen.append([(r["caller"], r["status"]) for r in rows()])
        return 200, {"answers": {"q": {"type": "noul", "noul": 0.8}}, "usage": {"input_tokens": 50}}

    status, noul, _ = harness.ask_jev(QUESTION, "state", "k", post=post)
    assert status == 200
    assert seen == [[("evals.jev_constitution", "attempted")]]
    assert rows()[0]["actual_usd"] == pytest.approx(50 * PRICE)


def test_harness_sends_nothing_when_the_ledger_is_unwritable(tmp_path, monkeypatch):
    unwritable(tmp_path, monkeypatch)
    posts = []
    assert harness.ask_jev(QUESTION, "state", "k", post=lambda b, k: posts.append(1) or (200, {})) == (0, None, 0.0)
    assert posts == []


def test_triage_records_before_the_request(tmp_path):
    seen = []

    def transport(body, key):
        seen.append([(r["caller"], r["status"]) for r in rows()])
        return {"answers": {"j1": {"choice": "REAL_DATA"}}, "usage": {"input_tokens": 40}, "model": "m"}

    row = triage.evaluate(SNAP, triage_ledger(tmp_path), transport, "k")
    assert row["status"] == "OK"
    assert seen == [[("jev_triage", "attempted")]]
    assert rows()[0]["actual_usd"] == pytest.approx(40 * PRICE)


def test_triage_keeps_the_reserve_when_the_transport_raises(tmp_path):
    def transport(body, key):
        raise TimeoutError("slow")

    assert triage.evaluate(SNAP, triage_ledger(tmp_path), transport, "k")["status"] == "NOT_EVALUATED"
    (row,) = rows()
    assert row["status"] == "error" and row["actual_usd"] is None and row["reserved_usd"] > 0


def test_triage_sends_nothing_and_stops_the_batch_when_the_ledger_is_unwritable(tmp_path, monkeypatch):
    out = tmp_path / "labels.jsonl"
    unwritable(tmp_path, monkeypatch)
    sent = []
    n = triage.run([SNAP, dict(SNAP, run_id="r2")], out, triage_ledger(tmp_path), lambda b, k: sent.append(1) or {}, "k")
    assert sent == []
    assert n == 1
    assert json.loads(out.read_text())["status"] == "SPEND_UNRECORDED"


def test_shadow_records_both_ledgers_before_the_request_and_settles_both(tmp_path):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    seen = []

    def opener(req, timeout):
        seen.append(([r["status"] for r in rows()], [r["status"] for r in rows(legacy)]))
        return shadow_reply(2000)

    receipt = shadow.run_line(SHADOW_SNAP, live=True, key="k", ledger=legacy, opener=opener)
    assert receipt.get("reason") is None
    assert seen == [(["attempted"], ["attempted"])]
    (canon,), (own,) = rows(), rows(legacy)
    assert own["spend_id"] == canon["id"] and canon["caller"] == "mission_control_jev_shadow"
    assert canon["actual_usd"] == pytest.approx(2000 * PRICE) == own["actual_usd"]


def test_shadow_sends_nothing_when_the_machine_ledger_is_unwritable(tmp_path, monkeypatch):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    unwritable(tmp_path, monkeypatch)
    opened = []
    receipt = shadow.run_line(SHADOW_SNAP, live=True, key="k", ledger=legacy,
                              opener=lambda r, t: opened.append(1) or shadow_reply())
    assert receipt["reason"] == "SPEND_LEDGER_UNAVAILABLE"
    assert opened == []
    (own,) = rows(legacy)
    assert own["status"] == "refused" and own["actual_usd"] == 0


def test_a_call_the_tools_own_cap_refuses_never_reaches_the_machine_ledger(tmp_path):
    legacy = tmp_path / "skill-router-ledger.sqlite"
    assert shadow.reserve_call(legacy, shadow.RESERVED_INPUT_TOKENS_PER_CALL, cap=1e-9) is None
    assert rows() == []


def test_router_mirror_is_named_skill_router(tmp_path):
    legacy = tmp_path / "skill-router-ledger.sqlite"
    call_id = shadow.reserve_call(legacy, shadow.RESERVED_INPUT_TOKENS_PER_CALL)
    shadow.finish_call(legacy, call_id, "answered", 300)
    (canon,) = rows()
    assert canon["caller"] == "skill_router" and canon["input_tokens"] == 300


def test_default_jev_records_before_the_request_and_refuses_on_an_unwritable_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-not-a-key")
    seen = []

    def evaluate(payload, key, opener=None):
        seen.append([r["status"] for r in rows()])
        return {"usage": {"input_tokens": 7}}

    monkeypatch.setattr(shadow, "evaluate", evaluate)
    skill_router.default_jev()({"q": 1})
    assert seen == [["attempted"]]
    unwritable(tmp_path, monkeypatch)
    with pytest.raises(spend.SpendUnrecorded):
        skill_router.default_jev()({"q": 1})
    assert len(seen) == 1


def test_a_machine_cap_stops_the_call_that_would_exceed_it(monkeypatch):
    monkeypatch.setenv("JEV_DAILY_CAP_USD", str(2 * client.RESERVE_USD + 1e-9))
    posts = []

    def post(body, timeout):
        posts.append(1)
        return 200, {"answers": {}}, None  # no usage: each row keeps its full reserve

    assert "data" in client.send(BODY, post, budget())
    assert "data" in client.send(BODY, post, budget())
    assert client.send(BODY, post, budget()) == {"error": "spend_cap_reached"}
    assert len(posts) == 2


def test_unset_cap_is_uncapped():
    for _ in range(5):
        spend.reserve("t", 100.0)
    assert len(rows()) == 5


def test_sixteen_processes_reserving_at_once_lose_nothing():
    code = "from jev_platform import spend\nfor _ in range(5): spend.reserve('p', 0.001)\n"
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    procs = [subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stderr=subprocess.PIPE) for _ in range(16)]
    errors = [p.communicate(timeout=120)[1].decode() for p in procs]
    assert [p.returncode for p in procs] == [0] * 16, errors
    ids = [r["id"] for r in rows()]
    assert len(ids) == 80 == len(set(ids))
