"""Integration: cfo.approve_spend + draft_review.post_draft repointed onto
the autonomous reversibility gate (swarm.nexus.policy).

- approve_spend sources its auto/HITL split from classify_policy and threads
  reversibility into post_draft.
- post_draft short-circuits the human gate for reversible (auto-tier) drafts
  and sends immediately (honouring TAO_SWARM_ENABLED); medium/high keep HITL.
"""
from __future__ import annotations

import pytest

from swarm import cfo
from swarm import draft_review


# ---- cfo.approve_spend ----

def test_spend_under_ceiling_auto_approves():
    captured = {}

    def fake_post_draft(**kw):
        captured.update(kw)
        return {"draft_id": "d1"}

    d = cfo.approve_spend(
        amount_usd=200.0, vendor="OpenRouter", business_id="biz1",
        justification="tokens", post_draft=fake_post_draft,
    )
    assert d.status == "approved"
    assert captured == {}          # HITL never invoked for reversible spend


def test_spend_over_ceiling_routes_to_hitl_with_reversibility():
    captured = {}

    def fake_post_draft(**kw):
        captured.update(kw)
        return {"draft_id": "d2"}

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
