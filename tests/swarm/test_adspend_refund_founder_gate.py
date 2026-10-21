"""Ad spend (CMO) and customer refunds (CS) auto-approve nothing.

Founder decision 21/10/2026 ("NIL to both"): every amount waits for the
founder. The old autonomous ceilings were $5,000/day of ad spend and $100 per
refund; amounts either side of them, exactly at them, $0, negative,
non-finite, huge and non-numeric must all go to draft_review at an
approval-tier reversibility, and no env var may switch auto-approval back on.
"""
from __future__ import annotations

import inspect

import pytest

from swarm import audit_emit, cmo, config, cs, draft_review
from swarm.bots import cmo as cmo_bot
from swarm.bots import cs as cs_bot

ADSPEND_AMOUNTS = [0.01, 1.0, 4999.99, 5000.0, 5000.01, 1e12,
                   0.0, -50.0, float("nan"), float("inf"), float("-inf"), "50"]
REFUND_AMOUNTS = [0.01, 1.0, 99.99, 100.0, 100.01, 1e12,
                  0.0, -50.0, float("nan"), float("inf"), float("-inf"), "50"]
BOT_AMOUNTS = [0.0, 1.0, 100.0, 5000.0]


def _recorder():
    calls = []

    def fake_post_draft(**kw):
        calls.append(kw)
        return {"draft_id": "d1"}

    return calls, fake_post_draft


def _adspend(amount, post_draft=None):
    return cmo.approve_adspend(
        amount_usd_per_day=amount, channel="google-ads", business_id="biz1",
        justification="test", post_draft=post_draft,
    )


def _refund(amount, post_draft=None):
    return cs.approve_refund(
        amount_usd=amount, customer_id="cust-1", business_id="biz1",
        justification="test", post_draft=post_draft,
    )


# ---- no ceiling survives -------------------------------------------------

def test_ceiling_constants_and_parameters_are_gone():
    assert not hasattr(cmo, "AUTONOMOUS_ADSPEND_CEILING_USD_PER_DAY")
    assert not hasattr(cs, "AUTONOMOUS_REFUND_CEILING_USD")
    assert "spend_ceiling" not in inspect.signature(cmo.approve_adspend).parameters
    assert "refund_ceiling" not in inspect.signature(cs.approve_refund).parameters


# ---- every amount routes to draft_review at an approval tier -------------

@pytest.mark.parametrize("amount", ADSPEND_AMOUNTS, ids=repr)
def test_every_adspend_routes_to_draft_review(amount):
    calls, fake = _recorder()
    d = _adspend(amount, fake)
    assert d.status == "pending"
    assert d.draft_id == "d1"
    assert len(calls) == 1
    assert calls[0]["reversibility"] == "high"   # approval tier, never auto
    assert calls[0]["drafted_by_role"] == "CMO"


@pytest.mark.parametrize("amount", REFUND_AMOUNTS, ids=repr)
def test_every_refund_routes_to_draft_review(amount):
    calls, fake = _recorder()
    d = _refund(amount, fake)
    assert d.status == "pending"
    assert d.draft_id == "d1"
    assert len(calls) == 1
    assert calls[0]["reversibility"] == "high"   # approval tier, never auto
    assert calls[0]["drafted_by_role"] == "CS"


@pytest.mark.parametrize("amount", ADSPEND_AMOUNTS, ids=repr)
def test_no_provider_blocks_every_adspend(amount):
    assert _adspend(amount).status == "blocked"


@pytest.mark.parametrize("amount", REFUND_AMOUNTS, ids=repr)
def test_no_provider_blocks_every_refund(amount):
    assert _refund(amount).status == "blocked"


# ---- real draft_review in TEST_MODE: nothing is auto-sent ----------------

@pytest.fixture
def real_review(tmp_path, monkeypatch):
    """Real draft_review.post_draft in TEST_MODE, state in tmp, audit captured."""
    monkeypatch.setattr(config, "SWARM_LOG_DIR", tmp_path)
    monkeypatch.setattr(draft_review, "TEST_MODE", True)
    events, results = [], []
    monkeypatch.setattr(audit_emit, "row", lambda ev, *a, **k: events.append(ev))
    real_post = draft_review.post_draft

    def spy(**kw):
        results.append(real_post(**kw))
        return results[-1]

    monkeypatch.setattr(draft_review, "post_draft", spy)
    return events, results


def _assert_waited_for_human(events, results, expected):
    assert len(results) == expected
    for r in results:
        assert r["status"] == "pending"          # posted for review, not "sent"
        assert r.get("policy_level") != "auto"
    assert "draft_auto_approved" not in events
    assert "cmo_adspend_approved" not in events
    assert "cs_refund_approved" not in events


@pytest.mark.parametrize("amount", BOT_AMOUNTS)
def test_real_draft_review_holds_adspend_and_refund(amount, real_review):
    events, results = real_review
    assert _adspend(amount, draft_review.post_draft).status == "pending"
    assert _refund(amount, draft_review.post_draft).status == "pending"
    _assert_waited_for_human(events, results, expected=2)


# ---- bot entry points: env ceilings are ignored, no *_approved event -----

def test_bot_env_ceilings_cannot_reenable_auto_approve(real_review, monkeypatch):
    events, results = real_review
    monkeypatch.setenv("TAO_CMO_ADSPEND_CEILING", "1000000000000000")
    monkeypatch.setenv("TAO_CS_REFUND_CEILING", "1000000000000000")
    for amount in BOT_AMOUNTS:
        d1 = cmo_bot.request_adspend_approval(
            amount_usd_per_day=amount, channel="meta", business_id="biz1",
            justification="test",
        )
        d2 = cs_bot.request_refund_approval(
            amount_usd=amount, customer_id="cust-1", business_id="biz1",
            justification="test",
        )
        assert d1.status == "pending"
        assert d2.status == "pending"
    _assert_waited_for_human(events, results, expected=2 * len(BOT_AMOUNTS))
    assert events.count("cmo_adspend_blocked") == len(BOT_AMOUNTS)
    assert events.count("cs_refund_blocked") == len(BOT_AMOUNTS)
