"""Tests for greeting.py — first-contact card with 2-row keyboard + scope-separation note.

Per ADR 003: greeting embeds the 2-row keyboard layout and documents both
pause modes + scope separation ("L4 digest runs regardless of pause-state").
"""
from swarm.pilot import greeting


def test_greeting_keyboard_has_two_rows():
    card = greeting.first_contact_card()
    kb = card["reply_markup"]["inline_keyboard"]
    assert len(kb) == 2


def test_greeting_row1_has_agree_dismiss_discuss():
    card = greeting.first_contact_card()
    row1 = card["reply_markup"]["inline_keyboard"][0]
    labels = [b["text"] for b in row1]
    assert any("Agree" in l for l in labels)
    assert any("Dismiss" in l for l in labels)
    assert any("Discuss" in l for l in labels)


def test_greeting_row2_has_pause_and_stop():
    card = greeting.first_contact_card()
    row2 = card["reply_markup"]["inline_keyboard"][1]
    labels = [b["text"] for b in row2]
    assert any("PAUSE" in l for l in labels)
    assert any("STOP" in l for l in labels)


def test_greeting_text_documents_two_row_keyboard():
    card = greeting.first_contact_card()
    text = card["text"]
    assert "Agree" in text and "Dismiss" in text and "Discuss" in text
    assert "PAUSE 24h" in text and "STOP" in text


def test_greeting_text_documents_scope_separation():
    """ADR 003 §3: L4 digest must survive pause-state."""
    card = greeting.first_contact_card()
    text = card["text"]
    assert "L4" in text or "digest" in text.lower()
    assert "RESUME" in text


def test_greeting_text_removes_broken_contract_phrase():
    """The V0 'Reply STOP to pause' phrase promised a missing handler."""
    card = greeting.first_contact_card()
    assert "Reply STOP to pause" not in card["text"]


def test_greeting_callback_data_uses_noop_fingerprint():
    """Greeting buttons use a sentinel fingerprint since there's no suggestion."""
    card = greeting.first_contact_card()
    all_buttons = [b for row in card["reply_markup"]["inline_keyboard"] for b in row]
    for btn in all_buttons:
        assert "|" in btn["callback_data"]
