"""tests/test_closed_loop_intake.py — UNI-2214 slice 2: intake without Phill.

The spine (slice 1, #398) drains its own trigger queue but nothing FEEDS it in
production, so the loop never runs unless Phill enqueues by hand. This slice
wires the first real producer: the Chief-of-Staff ``flow`` intent — a multi-step
Telegram request — enqueues a closed-loop trigger so the orchestrator's existing
drain runs the full cycle on its next iteration, with zero manual orchestration.

The wiring is additive (the HITL draft ack still posts) and self-gates on
``config.CLOSED_LOOP_ENABLED`` — exactly the flag the orchestrator drain gates
on — so it is a no-op until the loop is switched on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import closed_loop as CL  # noqa: E402
from swarm import config as CFG  # noqa: E402
from swarm.bots import chief_of_staff as COS  # noqa: E402


@pytest.fixture
def spy_enqueue(monkeypatch):
    """Capture closed_loop.enqueue_trigger calls; never touch the real queue."""
    calls: list[dict] = []

    def _fake(trigger_text, *, repo_root=None, chat_id=None):
        calls.append({"trigger": trigger_text, "chat_id": chat_id})

    monkeypatch.setattr(CL, "enqueue_trigger", _fake)
    return calls


@pytest.fixture(autouse=True)
def _stub_draft(monkeypatch):
    """Stub the HITL post so _route has no Telegram/file side effects."""
    from swarm import draft_review
    monkeypatch.setattr(
        draft_review, "post_draft",
        lambda **kw: {"draft_id": "drf-test", "status": "pending"},
    )


def _flow_payload() -> dict:
    return {
        "intent": "flow",
        "confidence": 0.8,
        "fields": {"raw_steps_text": "research X then file a ticket then email Duncan"},
        "raw_message": "research X then file a ticket then email Duncan",
        "originating_chat_id": "12345",
        "originating_message_id": "678",
    }


def test_flow_intent_enqueues_when_loop_enabled(monkeypatch, spy_enqueue):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_ENABLED", True)

    action = COS._route(_flow_payload())

    # The real intake producer fired exactly once with the raw text + chat_id.
    assert len(spy_enqueue) == 1
    assert spy_enqueue[0]["trigger"] == "research X then file a ticket then email Duncan"
    assert spy_enqueue[0]["chat_id"] == "12345"

    # The HITL acknowledgment is still returned (wiring is additive).
    assert action.get("status") == "pending"


def test_flow_intent_is_noop_when_loop_disabled(monkeypatch, spy_enqueue):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_ENABLED", False)

    action = COS._route(_flow_payload())

    # Disabled flag → no enqueue → identical to the pre-slice Wave-2 behaviour.
    assert spy_enqueue == []
    assert action.get("status") == "pending"


def test_non_flow_intent_never_enqueues(monkeypatch, spy_enqueue):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_ENABLED", True)

    COS._route({
        "intent": "ticket",
        "confidence": 0.9,
        "fields": {"team_hint": "UNI", "title_hint": "x"},
        "raw_message": "file a ticket",
        "originating_chat_id": "12345",
        "originating_message_id": "9",
    })

    # Only the flow intent is a closed-loop producer in this slice.
    assert spy_enqueue == []
