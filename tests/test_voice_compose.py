"""tests/test_voice_compose.py — RA-1866 (B3) voice composer smoke."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import voice_compose as VC  # noqa: E402


# ── Text transforms ────────────────────────────────────────────────────────


def test_strip_emoji():
    assert "💰 CFO daily" not in VC._strip_emoji("💰 CFO daily")
    assert "CFO daily" in VC._strip_emoji("💰 CFO daily")


def test_normalise_currency_integer():
    assert "1,000 dollars" in VC._normalise_currency("$1,000 budget")


def test_normalise_currency_decimal():
    assert "1,250.50 dollars" in VC._normalise_currency("$1,250.50 deal")


def test_normalise_percentage():
    assert "99.99 percent" in VC._normalise_percentage("uptime 99.99%")
    assert "12 percent" in VC._normalise_percentage("CFR 12%")


def test_normalise_abbreviations_mrr():
    out = VC._normalise_abbreviations("Total MRR is steady; NRR drift.")
    assert "M R R" in out
    assert "N R R" in out


def test_normalise_abbreviations_dora():
    out = VC._normalise_abbreviations("DORA quartet shows MTTR and CFR.")
    assert "D O R A" in out
    assert "mean time to recover" in out
    assert "change failure rate" in out


def test_spoken_section_transitions():
    text = "1. CFO daily\n2. CMO daily\n3. CTO daily"
    out = VC._spoken_section_transitions(text)
    assert "Section 1 of 6: CFO daily" in out
    assert "Section 2 of 6: CMO daily" in out


def test_strip_bullets():
    out = VC._strip_bullets("- foo\n* bar\n— —\n• baz")
    assert "foo" in out
    assert "bar" in out
    assert "baz" in out
    assert "- foo" not in out
    assert "* bar" not in out


def test_voice_friendly_text_end_to_end():
    """Compose all transforms in one happy-path string."""
    brief = (
        "📋 Pi-CEO daily 6-pager — 2026-05-02\n\n"
        "1. 💰 CFO daily — burn / runway\n"
        "Total MRR: $12,500 | Avg uptime: 99.95%\n"
        "- restoreassist: $4,200 spend\n"
        "—\n"
        "2. 📈 CMO daily — channel mix\n"
    )
    out = VC.voice_friendly_text(brief)
    # No emojis
    assert "💰" not in out and "📋" not in out
    # Section transitions
    assert "Section 1 of 6:" in out
    # Currency normalised
    assert "12,500 dollars" in out
    assert "4,200 dollars" in out
    # Percentage normalised
    assert "99.95 percent" in out
    # Abbreviation expanded
    assert "M R R" in out
    # Bullets flattened
    assert "- restoreassist" not in out
    assert "restoreassist" in out


# ── synthesise_voice without API key ────────────────────────────────────────


def test_synthesise_voice_no_api_key_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    result = VC.synthesise_voice("hello", out_path=tmp_path / "x.mp3")
    assert result is None


def test_synthesise_voice_explicit_empty_key_returns_none(tmp_path):
    result = VC.synthesise_voice(
        "hello", out_path=tmp_path / "x.mp3", api_key="",
    )
    assert result is None


# ── compose_voice_variant ───────────────────────────────────────────────────


def test_compose_voice_variant_no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    text, audio = VC.compose_voice_variant(
        "📋 Pi-CEO daily 6-pager — 2026-05-02\n\n1. 💰 CFO daily",
        out_dir=tmp_path / "voice",
    )
    assert audio is None
    assert "Section 1 of 6:" in text
    assert "📋" not in text


def test_compose_voice_variant_with_mocked_synth(monkeypatch, tmp_path):
    """Patch synthesise_voice to simulate a successful TTS write."""
    written_path = tmp_path / "voice" / "six-pager.mp3"

    def fake_synth(text, *, out_path, voice_id=None, api_key=None):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00\x01fake-mp3")
        return out_path

    monkeypatch.setattr(VC, "synthesise_voice", fake_synth)
    text, audio = VC.compose_voice_variant(
        "1. CFO daily — Total MRR $1,000",
        out_dir=tmp_path / "voice",
    )
    assert audio == written_path
    assert audio.exists()
    assert "1,000 dollars" in text
