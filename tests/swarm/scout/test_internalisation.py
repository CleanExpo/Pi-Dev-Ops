import pytest
from swarm.scout.internalisation_pipeline import generate_synthex_brief


def test_generate_synthex_brief_returns_dict_with_required_fields():
    scout_ticket = {
        "id": "SYN-001",
        "title": "Competitor X launched: 7-day water-damage SLA promise",
        "body": "Restoration Industries Aus published a 7-day SLA on their\nhomepage. Lead capture form mentions IICRC-WRT-certified\ntechnicians within 4h response. ANZ market.",
        "labels": ["[SCOUT]", "internalise-via-synthex"],
    }
    brief = generate_synthex_brief(scout_ticket)
    assert "title" in brief
    assert "voice_spec" in brief
    assert brief["voice_spec"] == "nexus-human-voice-2026-05-11"
    assert "named_operator" in brief
    assert "verdict_position" in brief
    assert brief["verdict_position"] == "last_20_percent"
    assert "forbidden_words_check" in brief
    assert brief["forbidden_words_check"] is True
