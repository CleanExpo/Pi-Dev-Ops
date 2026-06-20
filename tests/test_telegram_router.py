from __future__ import annotations

from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import telegram_router  # noqa: E402
from swarm.bots import chief_of_staff  # noqa: E402


def test_command_prefix_overrides_keyword_fallback():
    route = telegram_router.route_message("/cto research latest Cursor CLI deploy impact")

    assert route.specialist == "cto"
    assert route.persona == "CTO"
    assert route.action == "technical_strategy"
    assert route.confidence == 0.99


def test_fix_project_intent_routes_to_builder():
    payload = {"intent": "fix_project", "raw_message": "Fix RestoreAssist CI"}

    enriched = telegram_router.attach_route(payload)

    assert enriched["specialist_route"]["specialist"] == "builder"
    assert enriched["specialist_route"]["persona"] == "Builder"
    assert enriched["specialist_route"]["reason"] == "fix_project intent"


def test_mobile_second_brain_capture_routes_to_scribe():
    route = telegram_router.route_message(
        "Capture this Plaud transcript into Obsidian and summarise the idea"
    )

    assert route.specialist == "scribe"
    assert route.action == "capture_and_summarise"


def test_unknown_message_defaults_to_margot_assistant():
    route = telegram_router.route_message("Can you think this through with me?")

    assert route.specialist == "margot"
    assert route.confidence == 0.55


def test_cos_draft_includes_specialist_route(monkeypatch):
    captured: dict[str, str] = {}

    def fake_post_draft(**kwargs):
        captured.update(kwargs)
        return {"draft_id": "draft-1"}

    import swarm

    fake_draft_review = types.SimpleNamespace(post_draft=fake_post_draft)
    monkeypatch.setitem(sys.modules, "swarm.draft_review", fake_draft_review)
    monkeypatch.setattr(swarm, "draft_review", fake_draft_review, raising=False)

    result = chief_of_staff._route({
        "intent": "fix_project",
        "confidence": 0.9,
        "originating_chat_id": "123",
        "originating_message_id": "456",
        "fields": {"project_hint": "RestoreAssist", "raw_text": "Fix RestoreAssist CI"},
        "specialist_route": {
            "specialist": "builder",
            "persona": "Builder",
            "action": "autonomous_build_triage",
            "confidence": 0.88,
            "reason": "fix_project intent",
        },
    })

    assert result == {"draft_id": "draft-1"}
    assert "Specialist: Builder (autonomous_build_triage)" in captured["draft_text"]
