"""Tests for scripts/verify_margot_voice_stt.py (RA-1692)."""
from __future__ import annotations

import wave
from pathlib import Path

from scripts import verify_margot_voice_stt as vstt


def test_write_silence_wav_creates_mono_16k(tmp_path: Path) -> None:
    out = tmp_path / "silence.wav"
    vstt._write_silence_wav(out, duration_s=0.1, sample_rate=16_000)
    with wave.open(str(out), "r") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 16_000
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == 1600


def test_main_missing_python_json(tmp_path: Path) -> None:
    missing = tmp_path / "no-python"
    code = vstt.main(["--python", str(missing), "--json"])
    assert code == 1
