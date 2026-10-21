"""No draft sends itself (Codex FAIL on b021085d, P1-MONEY-WORDS-AUTO-SEND).

draft_review.post_draft used to auto-send a "reversible"/"low" draft unless a
money-word list matched; "Sending fifty to the vendor today." got through, and
no finite word list closes that. Every draft now waits for the founder's
reaction, whatever reversibility the caller claims. No checked-in caller asked
for the auto tier (the bots pass "medium" or "high"; no flow sets it); a flow
step could, through skill.telegram-draft-for-review. Same fixture as
test_founder_approval_path.py, with _do_send recorded, never real.
"""
from __future__ import annotations

import pytest

from swarm import draft_review

import test_founder_approval_path as base

env = base.env


@pytest.mark.parametrize("reversibility", ["reversible", "low", "medium", "high", "irreversible"])
@pytest.mark.parametrize("text", [
    "Thanks, the ticket is now closed.",
    "Sending fifty to the vendor today.",
    "We have bought the equipment for fifty thousand.",
    "The vendor bill is settled.",
    "Transfer AUD 50 to the vendor.",
    "We have waived the late fee.",
])
def test_no_draft_sends_without_the_founder(env, reversibility, text):
    out = draft_review.post_draft(draft_text=text, destination_chat_id="42",
                                  drafted_by_role="CS", reversibility=reversibility)
    assert out["status"] == "pending"
    assert out.get("policy_level") != "auto"
    assert env.sends == []
    assert draft_review._load_snapshot()[out["draft_id"]]["status"] == "pending"


def test_a_reversible_draft_is_still_posted_for_review(env, monkeypatch):
    cards = []
    monkeypatch.setattr(draft_review, "_post_review_message",
                        lambda text: cards.append(text) or "555")
    draft_review.post_draft(draft_text="Sending fifty to the vendor today.", destination_chat_id="42",
                            drafted_by_role="CS", reversibility="reversible")
    assert len(cards) == 1 and "Sending fifty to the vendor today." in cards[0]
