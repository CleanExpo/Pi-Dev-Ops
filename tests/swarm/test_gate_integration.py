"""Integration: cfo.approve_spend + draft_review.post_draft repointed onto
the autonomous reversibility gate (swarm.nexus.policy).

- approve_spend sends every amount to draft_review with an approval-tier
  reversibility; nothing is auto-approved (founder decision 21/10/2026).
- post_draft short-circuits the human gate for reversible (auto-tier) drafts
  and sends immediately (honouring TAO_SWARM_ENABLED); medium/high keep HITL.
"""
from __future__ import annotations

import pytest

from swarm import cfo
from swarm import draft_review


# ---- cfo.approve_spend ----
# Founder decision 21/10/2026: every amount goes to draft_review. The old
# autonomous ceiling was $1,000; amounts either side of it, exactly at it, $0,
# negative and non-finite must all wait for the founder.

ALL_AMOUNTS = [0.01, 200.0, 999.99, 1000.0, 1000.01, 5000.0,
               0.0, -50.0, float("nan"), float("inf")]


@pytest.mark.parametrize("amount", ALL_AMOUNTS)
def test_every_spend_routes_to_draft_review(amount):
    calls = []

    def fake_post_draft(**kw):
        calls.append(kw)
        return {"draft_id": "d1", "review_message_id": "m-d1", "status": "pending"}

    d = cfo.approve_spend(
        amount_usd=amount, vendor="OpenRouter", business_id="biz1",
        justification="tokens", post_draft=fake_post_draft,
    )
    assert d.status == "pending"
    assert d.draft_id == "d1"
    assert len(calls) == 1
    assert calls[0]["reversibility"] == "high"   # approval tier, never auto


@pytest.mark.parametrize("amount", ALL_AMOUNTS)
def test_no_provider_blocks_every_spend(amount):
    d = cfo.approve_spend(
        amount_usd=amount, vendor="OpenRouter", business_id="biz1",
        justification="tokens", post_draft=None,
    )
    assert d.status == "blocked"


@pytest.mark.parametrize("amount", [1.0, 1000.0, 0.0])
def test_small_spend_through_real_draft_review_waits_for_human(amount, monkeypatch):
    monkeypatch.setattr(draft_review, "TEST_MODE", True)
    d = cfo.approve_spend(
        amount_usd=amount, vendor="OpenRouter", business_id="biz1",
        justification="tokens", post_draft=draft_review.post_draft,
    )
    assert d.status == "pending"
    assert d.draft_id


def test_bot_env_ceiling_cannot_reenable_auto_approve(monkeypatch):
    from swarm import audit_emit
    from swarm.bots import cfo as cfo_bot

    events = []
    monkeypatch.setenv("TAO_CFO_SPEND_CEILING", "1000000000")
    monkeypatch.setattr(draft_review, "post_draft", lambda **kw: {"draft_id": "d9", "review_message_id": "m-d9", "status": "pending"})
    monkeypatch.setattr(audit_emit, "row", lambda ev, *a, **k: events.append(ev))
    for amount in (1.0, 1000.0, 0.0):
        d = cfo_bot.request_spend_approval(
            amount_usd=amount, vendor="OpenRouter", business_id="biz1",
            justification="tokens",
        )
        assert d.status == "pending"
    assert "cfo_invoice_approved" not in events
    assert events == ["cfo_spend_blocked"] * 3


def test_spend_over_ceiling_routes_to_hitl_with_reversibility():
    captured = {}

    def fake_post_draft(**kw):
        captured.update(kw)
        return {"draft_id": "d2", "review_message_id": "m-d2", "status": "pending"}

    d = cfo.approve_spend(
        amount_usd=5000.0, vendor="BigCorp", business_id="biz1",
        justification="annual license", post_draft=fake_post_draft,
    )
    assert d.status == "pending"
    assert d.draft_id == "d2"
    assert captured["reversibility"] == "high"   # threaded through to the gate


def test_spend_over_ceiling_no_provider_blocks():
    d = cfo.approve_spend(
        amount_usd=5000.0, vendor="BigCorp", business_id="biz1",
        justification="x", post_draft=None,
    )
    assert d.status == "blocked"


# ---- draft_review.post_draft ----

@pytest.fixture
def draft_test_mode(monkeypatch):
    monkeypatch.setattr(draft_review, "TEST_MODE", True)


@pytest.mark.parametrize("rev", ["reversible", "low"])
def test_post_draft_auto_tier_skips_human(rev, draft_test_mode):
    out = draft_review.post_draft(
        draft_text="routine status note",
        destination_chat_id="123",
        drafted_by_role="Scribe",
        reversibility=rev,
    )
    assert out["policy_level"] == "auto"
    assert out["review_message_id"] is None     # no human review posted
    assert out["status"] == "sent"              # auto-sent in TEST_MODE


@pytest.mark.parametrize("rev", ["medium", "high", "irreversible"])
def test_post_draft_non_auto_keeps_hitl(rev, draft_test_mode):
    out = draft_review.post_draft(
        draft_text="needs a human",
        destination_chat_id="123",
        drafted_by_role="Scribe",
        reversibility=rev,
    )
    assert out.get("policy_level") != "auto"
    assert out["review_message_id"] is not None  # posted for human review
    assert out["status"] == "pending"


def test_post_draft_default_is_hitl(draft_test_mode):
    # default reversibility="medium" preserves the pre-gate HITL behaviour
    out = draft_review.post_draft(
        draft_text="legacy caller, no reversibility passed",
        destination_chat_id="123",
        drafted_by_role="Scribe",
    )
    assert out["status"] == "pending"
    assert out["review_message_id"] is not None
