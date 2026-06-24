from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_voice_module_exists_and_names_synthex_source():
    text = (ROOT / "remotion-studio" / "render" / "single-voice.ts").read_text()

    assert "Synthex" in text
    assert "ELEVENLABS" in text
    assert "assertSingleVoice" in text
    assert "multiple voices" in text.lower()


def test_remotion_skills_document_single_voice_policy():
    for rel in [
        "skills/remotion-orchestrator/SKILL.md",
        "skills/remotion-integrations/SKILL.md",
        "skills/remotion-script/SKILL.md",
    ]:
        text = (ROOT / rel).read_text()
        assert "single voice" in text.lower(), rel
        assert "ElevenLabs" in text, rel
