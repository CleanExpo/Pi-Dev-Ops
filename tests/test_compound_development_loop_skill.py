from __future__ import annotations

from src.tao import skills


def test_compound_development_loop_loads_as_skill():
    skills.invalidate_cache()

    skill = skills.get_skill("compound-development-loop")

    assert skill is not None
    assert "Do not treat the operator's words as the full specification" in skill["body"]
    assert "scripts/idea_expansion.py" in skill["body"]
    assert skill["automation"] == "hybrid"


def test_compound_development_loop_is_injected_for_build_intents():
    skills.invalidate_cache()

    routed = {
        intent: [skill["name"] for skill in skills.skills_for_intent(intent)]
        for intent in ("feature", "spec", "plan", "spike")
    }

    assert routed["feature"][0] == "compound-development-loop"
    assert routed["spec"][0] == "compound-development-loop"
    assert routed["plan"][0] == "compound-development-loop"
    assert routed["spike"][0] == "compound-development-loop"
