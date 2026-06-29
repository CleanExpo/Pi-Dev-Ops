"""Tests for swarm.intake.forwarder.ProductionSpmForwarder."""
from __future__ import annotations

from swarm.intake.forwarder import ProductionSpmForwarder


class _RecordingBoard:
    """Records board submissions instead of running a deliberation."""

    def __init__(self, *, session_id: str = "board-sess-1", raises: bool = False):
        self.calls: list[dict] = []
        self._session_id = session_id
        self._raises = raises

    def __call__(self, *, topic: str, material: str, requested_decisions):
        self.calls.append(
            {"topic": topic, "material": material, "decisions": requested_decisions}
        )
        if self._raises:
            raise RuntimeError("board down")
        return self._session_id


def _forward(board, **overrides):
    fwd = ProductionSpmForwarder(submit_to_board=board)
    kwargs = dict(thread_id="t-1", project_id="p-9", bot_id="PiCeoDevBot", body="Build a CRM")
    kwargs.update(overrides)
    fwd.forward(**kwargs)
    return board


def test_forward_submits_one_deliberation():
    board = _forward(_RecordingBoard())
    assert len(board.calls) == 1


def test_topic_includes_project_and_message_head():
    board = _forward(_RecordingBoard())
    topic = board.calls[0]["topic"]
    assert "p-9" in topic
    assert "Build a CRM" in topic


def test_material_carries_routing_context():
    board = _forward(_RecordingBoard())
    material = board.calls[0]["material"]
    assert "PiCeoDevBot" in material
    assert "t-1" in material
    assert "p-9" in material
    assert "Build a CRM" in material


def test_default_decisions_are_passed():
    board = _forward(_RecordingBoard())
    decisions = board.calls[0]["decisions"]
    assert isinstance(decisions, list) and len(decisions) == 3
    assert any("specialist" in d for d in decisions)


def test_empty_body_still_submits_with_placeholder():
    board = _forward(_RecordingBoard(), body="")
    assert len(board.calls) == 1
    assert board.calls[0]["topic"] == "Intake project p-9"
    assert "(no message body)" in board.calls[0]["material"]


def test_board_failure_is_swallowed_fire_and_forget():
    board = _RecordingBoard(raises=True)
    # Must NOT raise — one bad hand-off can't crash the intake tick.
    _forward(board)
    assert len(board.calls) == 1


def test_custom_decisions_override():
    board = _RecordingBoard()
    fwd = ProductionSpmForwarder(submit_to_board=board, decisions=["Only question?"])
    fwd.forward(thread_id="t", project_id="p", bot_id="b", body="x")
    assert board.calls[0]["decisions"] == ["Only question?"]


def test_satisfies_spmforwarder_protocol():
    # Structural: the dispatcher type-checks against this Protocol.
    from swarm.inbox.intake_dispatch import SpmForwarder

    fwd: SpmForwarder = ProductionSpmForwarder(submit_to_board=_RecordingBoard())
    assert hasattr(fwd, "forward")
