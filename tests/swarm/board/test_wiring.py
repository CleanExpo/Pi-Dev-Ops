"""Tests for the Pi-CEO Board dispatcher (Wave 5.4 Phase B — LLM wiring)."""
from unittest.mock import patch

import pytest

from swarm.board.personas import CANONICAL_PERSONAS
from swarm.board.wiring import dispatch


def test_dispatch_returns_all_nine_personas():
    decision = dispatch("Should we accept a CCW upsell to NRPG seats?")
    assert len(decision.opinions) == len(CANONICAL_PERSONAS)
    assert "CEO" in decision.opinions
    assert "Contrarian" in decision.opinions
    assert decision.strategic_ask.startswith("Should we")


def test_dispatch_opinions_are_real_not_stubs():
    """Each non-CEO persona opinion must be a real LLM response.

    Real means: ≥100 chars, does not contain "stub", and does not start
    with "(" (which the Phase A placeholder used to wrap descriptions).
    """
    decision = dispatch(
        "Should we ship the RestoreAssist iOS App Store push this week "
        "or hold for the NRPG community launch?"
    )
    non_ceo = {r: o for r, o in decision.opinions.items() if r != "CEO"}
    assert len(non_ceo) == 8
    for role, opinion in non_ceo.items():
        assert len(opinion) >= 100, (
            f"{role} opinion too short ({len(opinion)} chars): {opinion!r}"
        )
        assert "stub" not in opinion.lower(), (
            f"{role} opinion still contains 'stub': {opinion!r}"
        )
        assert not opinion.lstrip().startswith("("), (
            f"{role} opinion looks like a placeholder: {opinion!r}"
        )


def test_ceo_decision_memo_cites_at_least_three_personas():
    """CEO synthesis must explicitly reference ≥3 of the 9 persona roles."""
    decision = dispatch(
        "Should we accept a CCW upsell to NRPG seats for an extra "
        "$15K/yr ARR, knowing it pulls engineering off the RA iOS push?"
    )
    memo = decision.decision_memo
    role_names = [p.role for p in CANONICAL_PERSONAS]
    hits = [r for r in role_names if r in memo]
    assert len(hits) >= 3, (
        f"CEO memo only cites {hits}; expected ≥3 of {role_names}.\n"
        f"Memo: {memo}"
    )


def test_dispatch_routing_extracts_pm_slug():
    """When the CEO synthesis includes [DISPATCH-TO: PM-RA], parser sets it."""
    # Mock the ollama call: persona prompts return generic content (≥100 chars);
    # the CEO synthesis prompt returns a memo containing the sentinel.
    fake_persona_opinion = (
        "This is a real-looking opinion that is comfortably over one "
        "hundred characters long so the dispatcher does not reject it "
        "as a stub during validation."
    )
    fake_ceo_memo = (
        "Decision: ship the RA iOS push first. Revenue and Product Strategist "
        "back the move; Contrarian's concern about CCW timing is acknowledged.\n"
        "[DISPATCH-TO: PM-RA]"
    )

    async def fake_call(*, prompt: str, model_id: str, **kwargs):
        # CEO synthesis prompts contain "DISPATCH-TO" guidance text.
        if "DISPATCH-TO" in prompt:
            return 0, fake_ceo_memo, 0.0, None
        return 0, fake_persona_opinion, 0.0, None

    with patch("swarm.board.wiring.ollama_call", new=fake_call):
        decision = dispatch("Ship RA iOS now or hold?")

    assert decision.dispatched_to == "PM-RA"
    # Rationale should describe the RestoreAssist routing, not be empty.
    assert decision.rationale
    assert "RestoreAssist" in decision.rationale


def test_dispatch_routing_none_sentinel_yields_no_pm():
    """When CEO emits [DISPATCH-TO: NONE], dispatched_to is None and a
    sensible rationale is returned. Replaces the old stub-era assertion."""
    fake_persona_opinion = (
        "This is a real-looking opinion that is comfortably over one "
        "hundred characters long so the dispatcher does not reject it "
        "as a stub during validation."
    )
    fake_ceo_memo = (
        "Decision: do nothing this cycle. Revenue, Compounder, and "
        "Contrarian all argue the timing is wrong; no implementation needed.\n"
        "[DISPATCH-TO: NONE]"
    )

    async def fake_call(*, prompt: str, model_id: str, **kwargs):
        if "DISPATCH-TO" in prompt:
            return 0, fake_ceo_memo, 0.0, None
        return 0, fake_persona_opinion, 0.0, None

    with patch("swarm.board.wiring.ollama_call", new=fake_call):
        decision = dispatch("Should we do this thing nobody wants?")

    assert decision.dispatched_to is None
    assert decision.rationale  # Non-empty explanation of the no-route choice.
