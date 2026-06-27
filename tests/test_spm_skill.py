from __future__ import annotations

from src.tao import skills


def test_spm_skill_loads_with_spec_not_build_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("spm")

    assert skill is not None
    assert "/spm" in skill["description"]
    assert "Senior Project Manager" in skill["body"]
    # Read-only spec author, not a builder.
    assert "No spec. No build." in skill["body"]
    assert "not a builder" in skill["body"]
    # Explicit-invoke gate.
    assert skill["automation"] == "manual"


def test_spm_intent_routes_to_spm_skill():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("spm")]

    assert routed == ["spm"]


def test_spm_classified_manual_in_manifest():
    skills.invalidate_cache()

    manifest = skills.skills_manifest()
    manual_names = {s["name"] for s in manifest["manual"]}
    auto_names = {s["name"] for s in manifest["auto"]}

    assert "spm" in manual_names
    assert "spm" not in auto_names
