from __future__ import annotations

from src.tao import skills


def test_resume_from_handoff_skill_loads_with_verify_then_resume_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("resume-from-handoff")

    assert skill is not None
    assert "/resume-from-handoff" in skill["description"]
    assert "Resume From a Session Handoff" in skill["body"]
    # Verification gate must be present and mandatory.
    assert "verify before you resume" in skill["body"]
    assert "read-only" in skill["body"]
    # Companion to the session-handoff command.
    assert "session-handoff" in skill["body"]
    # Explicit-invoke.
    assert skill["automation"] == "manual"


def test_resume_intent_routes_to_resume_from_handoff_skill():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("resume")]

    assert routed == ["resume-from-handoff"]


def test_resume_from_handoff_classified_manual_in_manifest():
    skills.invalidate_cache()

    manifest = skills.skills_manifest()
    manual_names = {s["name"] for s in manifest["manual"]}
    auto_names = {s["name"] for s in manifest["auto"]}

    assert "resume-from-handoff" in manual_names
    assert "resume-from-handoff" not in auto_names
