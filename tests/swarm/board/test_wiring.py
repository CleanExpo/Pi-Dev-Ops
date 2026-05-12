from swarm.board.wiring import dispatch
from swarm.board.personas import CANONICAL_PERSONAS


def test_dispatch_returns_all_nine_personas():
    decision = dispatch("Should we accept a CCW upsell to NRPG seats?")
    assert len(decision.opinions) == len(CANONICAL_PERSONAS)
    assert "CEO" in decision.opinions
    assert "Contrarian" in decision.opinions
    assert decision.strategic_ask.startswith("Should we")


def test_dispatch_records_dispatched_to_as_none_in_stub():
    decision = dispatch("Test")
    assert decision.dispatched_to is None  # Stub — Phase B will set this
