from __future__ import annotations

from pathlib import Path

from src.tao import skills

ROOT = Path(__file__).resolve().parents[1]


def test_remotion_orchestrator_skill_loads_command_contract():
    skills.invalidate_cache()

    skill = skills.get_skill("remotion-orchestrator")

    assert skill is not None
    assert "/remotion-video" in skill["description"]
    assert "one-shot" in skill["body"]
    assert "single voice" in skill["body"].lower()
    assert "ElevenLabs" in skill["body"]
    assert "no new vendors" in skill["body"]


def test_video_intent_routes_to_remotion_skill_family_first():
    skills.invalidate_cache()

    routed = [skill["name"] for skill in skills.skills_for_intent("video")]

    assert routed[:3] == [
        "remotion-orchestrator",
        "remotion-script",
        "remotion-production",
    ]
    assert "remotion-direction" in routed
    assert "remotion-editing" in routed
    assert "remotion-integrations" in routed
    assert "remotion-professionalism" in routed


def test_claude_remotion_video_command_exists():
    text = (ROOT / ".claude" / "commands" / "remotion-video.md").read_text()

    assert "/remotion-video" in text
    assert "single" in text.lower()
    assert "Synthex" in text
    assert "dry-run" in text.lower()
