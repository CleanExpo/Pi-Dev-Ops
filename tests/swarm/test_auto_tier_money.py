"""A reversible draft that mentions money never auto-sends (Codex helper
finding on 93ee19ff): it goes to the founder's review like any other money
draft. Non-money reversible drafts still auto-send. Uses the same fixture as
test_founder_approval_path.py, with _do_send recorded, never real.
"""
from __future__ import annotations

import pytest

from swarm import draft_review

import test_founder_approval_path as base

env = base.env


@pytest.mark.parametrize("text", [
    "CS confirms your $50 refund is approved.",
    "Your service credit has been applied to the account.",
    "We will reimburse the duplicate charge today.",
    "Payment of 200 AUD released to the vendor.",
    "Ad spend raised to 4,000 a day.",
    "Invoice INV-77 approved for payment.",
    "Your refund is on its way.",
])
def test_reversible_money_draft_goes_to_review(env, text):
    out = draft_review.post_draft(draft_text=text, destination_chat_id="42",
                                  drafted_by_role="CS", reversibility="reversible")
    assert out["status"] == "pending"
    assert out.get("policy_level") != "auto"
    assert env.sends == []


def test_reversible_non_money_draft_still_auto_sends(env):
    out = draft_review.post_draft(draft_text="Thanks, the ticket is now closed.",
                                  destination_chat_id="42", drafted_by_role="CS",
                                  reversibility="reversible")
    assert out["status"] == "sent"
    assert len(env.sends) == 1
