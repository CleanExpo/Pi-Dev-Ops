from __future__ import annotations

from src.tao import skills


def test_northstar_shipit_skill_loads_with_noise_removal_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("northstar-shipit")

    assert skill is not None
    assert skill["automation"] == "manual"
    assert "remove noise" in skill["body"].lower()
    assert "straight pathway to ShipIt" in skill["body"]
    assert "launch-charter" in skill["body"]
    assert "ship-it" in skill["body"]
    assert "No deploys" in skill["body"]


def test_northstar_intent_routes_before_shipit_chain():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("northstar")]

    assert routed[:2] == ["northstar-shipit", "launch-charter"]
    assert "ship-it" in routed
    assert "launch-project-audit" in routed
    assert "launch-review" in routed
    assert "launch-enhance-debloat" in routed
