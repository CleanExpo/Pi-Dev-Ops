from __future__ import annotations

from src.tao import skills


def test_review_command_skill_loads_with_review_only_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("review-command")

    assert skill is not None
    assert "/review" in skill["description"]
    assert "Review only" in skill["body"]
    assert "never fixes" in skill["body"]
    assert "launch-review" in skill["body"]
    assert "requesting-code-review" in skill["body"]


def test_review_intent_routes_to_specialised_review_first():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("review")]

    assert routed[:2] == ["review-command", "launch-review"]
    assert "agentic-review" in routed
    assert "tier-evaluator" in routed
    assert "leverage-audit" in routed
