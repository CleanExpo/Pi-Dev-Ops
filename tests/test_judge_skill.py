from __future__ import annotations

from src.tao import skills


def test_judge_skill_loads_with_read_only_gate_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("judge")

    assert skill is not None
    assert "/judge" in skill["description"]
    assert "Review only" in skill["body"]
    assert "never builds" in skill["body"]
    # Distinct from the machine loop-termination scorer.
    assert "tao-judge" in skill["body"]
    # Read-only, explicit-invoke gate.
    assert skill["automation"] == "manual"


def test_judge_intent_routes_to_judge_skill():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("judge")]

    assert routed == ["judge"]


def test_judge_classified_manual_in_manifest():
    skills.invalidate_cache()

    manifest = skills.skills_manifest()
    manual_names = {s["name"] for s in manifest["manual"]}
    auto_names = {s["name"] for s in manifest["auto"]}

    # Even though "judge" is intent-routed, automation:manual keeps it explicit-invoke.
    assert "judge" in manual_names
    assert "judge" not in auto_names
