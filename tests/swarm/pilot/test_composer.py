"""Tests for composer.py — 2-row InlineKeyboardMarkup payload builder.

Per ADR 003: Row 1 = Agree/Dismiss/Discuss; Row 2 = PAUSE 24h / STOP.
Per ADR 001: pillar rendered as chip-array.
"""
from swarm.pilot import composer
from swarm.pilot.types import RawCandidate


def _c(headline="PR #226 green 18h, merge?", pillar=None):
    return RawCandidate(
        fingerprint="fp1", headline=headline,
        pillar=pillar or ["Tier-2 Infra"],
        effort="XS", source="github", confidence="HIGH",
        body={}, impact_score=80,
    )


def test_keyboard_has_two_rows():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    assert len(kb) == 2


def test_row1_three_buttons_agree_dismiss_discuss():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    labels = [b["text"] for b in kb[0]]
    assert len(kb[0]) == 3
    assert any("Agree" in l for l in labels)
    assert any("Dismiss" in l for l in labels)
    assert any("Discuss" in l for l in labels)


def test_row2_two_buttons_pause_and_stop():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    labels = [b["text"] for b in kb[1]]
    assert len(kb[1]) == 2
    assert any("PAUSE" in l for l in labels)
    assert any("STOP" in l for l in labels)


def test_callback_data_shape_action_pipe_fingerprint():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    agree = next(b for r in kb for b in r if "Agree" in b["text"])
    assert agree["callback_data"] == "agree|fp1"
    stop = next(b for r in kb for b in r if "STOP" in b["text"])
    assert stop["callback_data"] == "stop|fp1"


def test_pillar_array_renders_as_chips():
    c = _c(pillar=["Restoration", "CARSI"])
    text = composer.format(c)["text"]
    assert "Restoration" in text and "CARSI" in text


def test_headline_truncated_at_80():
    long = "x" * 200
    first = composer.format(_c(headline=long))["text"].split("\n", 1)[0]
    assert len(first) <= 80
