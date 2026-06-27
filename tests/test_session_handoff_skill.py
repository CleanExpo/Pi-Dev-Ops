from __future__ import annotations

from src.tao import skills


def test_session_handoff_skill_loads_with_read_only_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("session-handoff")

    assert skill is not None
    assert "/session-handoff" in skill["description"]
    assert "Review/report only" in skill["body"]
    assert "never edits" in skill["body"]
    # Companion to the judge gate.
    assert "judge" in skill["body"]
    # Read-only, explicit-invoke gate.
    assert skill["automation"] == "manual"


def test_handoff_intent_routes_to_session_handoff_skill():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("handoff")]

    assert routed == ["session-handoff"]


def test_session_handoff_classified_manual_in_manifest():
    skills.invalidate_cache()

    manifest = skills.skills_manifest()
    manual_names = {s["name"] for s in manifest["manual"]}
    auto_names = {s["name"] for s in manifest["auto"]}

    # Even though "session-handoff" is intent-routed, automation:manual keeps it
    # explicit-invoke.
    assert "session-handoff" in manual_names
    assert "session-handoff" not in auto_names
