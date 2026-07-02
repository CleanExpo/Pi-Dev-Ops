"""Tests for Margot voice verification scripts."""
from __future__ import annotations

from pathlib import Path

from scripts import verify_margot_voice_tts as vtts


def test_verify_tts_no_api_key_json(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    code = vtts.main(["--json"])
    assert code == 1


def test_verify_tts_success(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    def fake_synth(text: str, *, out_path: Path, **kwargs):
        out_path.write_bytes(b"mp3")
        return out_path

    monkeypatch.setattr(vtts.VC, "synthesise_voice", fake_synth)
    code = vtts.main(["--json", "--text", "hi"])
    assert code == 0
