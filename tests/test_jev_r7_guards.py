"""UNI-3087 review round 7: the triage side cap is checked against the reserve a request really
takes, and a reply that is not an object is NOT_EVALUATED, never a crash. Offline fakes only."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from jev_platform import client
from tests.jev_spend_support import rows

_spec = importlib.util.spec_from_file_location(
    "jev_triage", Path(__file__).resolve().parent.parent / "scripts" / "jev_triage.py")
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)

SNAP = {"run_id": "r1", "sha": "abc", "surface": "/s", "contract": "J1", "page_text": "hello", "network": []}


def _transport(reply):
    calls = []

    def transport(body, key):
        calls.append(1)
        return reply
    return transport, calls


def test_side_cap_below_one_reserve_sends_nothing_and_reserves_nothing(tmp_path):
    """The estimate for this snapshot is far below RESERVE_USD. A cap with room for the estimate but
    not for the reserve must stop before the machine ledger is written or a request leaves."""
    body = jt.build_body(SNAP)
    estimate_usd = jt.estimate_tokens(body["state"] + str(body["questions"])) * jt.PRICE_PER_MTOK_INPUT / 1e6
    assert estimate_usd < client.RESERVE_USD / 2, "fixture: estimate must be well below one reserve"
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-11-08", cap=client.RESERVE_USD / 2)
    transport, calls = _transport({"answers": {}, "usage": {"input_tokens": 10}})
    out = jt.evaluate(SNAP, ledger, transport, "k")
    assert out["status"] == "BUDGET_STOP"
    assert calls == [], "a request left although one reserve exceeds the side cap"
    assert rows() == [], "the machine ledger reserved a call the side cap cannot cover"
    assert ledger.spent == 0.0


@pytest.mark.parametrize("reply", [
    ["not", "an", "object"],
    "a string",
    7,
    {"answers": ["j1"], "usage": {"input_tokens": 10}},
    {"answers": "j1", "usage": {"input_tokens": 10}},
])
def test_reply_or_answers_that_is_not_an_object_is_not_evaluated(tmp_path, reply):
    ledger = jt.Ledger(tmp_path / "spend.json", "2026-11-08", cap=None)
    transport, calls = _transport(reply)
    out = jt.evaluate(SNAP, ledger, transport, "k")
    assert calls == [1]
    assert out["status"] == "NOT_EVALUATED" and out["answer"] is None and out["model"] is None
    settled = rows()
    assert len(settled) == 1 and settled[0]["status"] != "attempted", "the reserved row was never settled"
    believable = isinstance(reply, dict)  # these carry valid usage: the real cost is counted, not the reserve
    want = 10 * client.USD_PER_TOKEN if believable else client.RESERVE_USD
    assert ledger.spent == pytest.approx(want), "the side ledger did not count what the machine ledger counts"
