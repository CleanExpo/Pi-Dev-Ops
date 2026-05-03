"""tests/test_portfolio_pulse_telegram.py — RA-1893.

Coverage:
  * deliver_to_telegram() chunks long pulses to <= CHUNK_BUDGET
  * Each chunk hits telegram_alerts.send with chat_id + bot_name="Margot"
  * No chat id (arg + env both missing) returns sent=False, no raise
  * Per-chunk failure surfaces in result.errors
  * Voice skipped when MARGOT_VOICE_REPLY_ENABLED unset
  * Voice attached on last chunk when enabled and synthesis present
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from swarm import portfolio_pulse_telegram as ppt  # noqa: E402


# -- Fixtures ----------------------------------------------------------------


class _FakeTelegram:
    """Records every send() call so tests can assert kwargs."""

    def __init__(self, fail_indices: tuple[int, ...] = ()):
        self.calls: list[dict] = []
        self.fail_indices = set(fail_indices)

    def send(self, text, **kwargs):  # noqa: D401
        idx = len(self.calls)
        self.calls.append({"text": text, **kwargs})
        if idx in self.fail_indices:
            raise RuntimeError(f"simulated failure for chunk {idx}")
        return True


@pytest.fixture
def fake_telegram(monkeypatch):
    fake = _FakeTelegram()
    module = types.ModuleType("swarm.telegram_alerts")
    module.send = fake.send  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "swarm.telegram_alerts", module)
    return fake


# -- Tests -------------------------------------------------------------------


def test_send_called_with_chat_id_and_bot_name(monkeypatch, fake_telegram):
    """Single short pulse -> one chunk sent with chat_id and Margot bot."""
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    result = ppt.deliver_to_telegram(
        "# pi-ceo — Portfolio Pulse 2026-05-03\n\nshort body",
        chat_id="999",
    )
    assert result["sent"] is True
    assert result["chunks"] == 1
    assert result["voice_attached"] is False
    assert result["errors"] == []
    assert len(fake_telegram.calls) == 1
    call = fake_telegram.calls[0]
    assert call["chat_id"] == "999"
    assert call["bot_name"] == "Margot"
    assert call["severity"] == "info"
    assert "short body" in call["text"]


def test_chunking_respects_budget(monkeypatch, fake_telegram):
    """A 10000-char pulse splits into >= 3 chunks, each <= CHUNK_BUDGET."""
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    # Build a synthetic pulse with multiple H2 sections so the section-
    # aware splitter has anchor points; pad each section to ~3000 chars.
    sections = []
    for i in range(4):
        sections.append(f"## Section {i}\n\n" + ("x" * 2900))
    pulse = "\n\n".join(sections)
    assert len(pulse) >= 10000

    result = ppt.deliver_to_telegram(pulse, chat_id="42", voice=False)

    assert result["sent"] is True
    assert result["chunks"] >= 3
    assert len(fake_telegram.calls) == result["chunks"]
    for call in fake_telegram.calls:
        assert len(call["text"]) <= ppt.CHUNK_BUDGET


def test_no_chat_id_returns_sent_false(monkeypatch):
    """Both arg None and env unset -> sent=False, no raise, no calls."""
    monkeypatch.delenv("MARGOT_DM_CHAT_ID", raising=False)
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    result = ppt.deliver_to_telegram("anything", chat_id=None)
    assert result["sent"] is False
    assert result["error"] == "no_chat_id"
    assert result["chunks"] == 0


def test_chat_id_falls_back_to_env(monkeypatch, fake_telegram):
    monkeypatch.setenv("MARGOT_DM_CHAT_ID", "env-chat-77")
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    result = ppt.deliver_to_telegram("hello", voice=False)
    assert result["sent"] is True
    assert fake_telegram.calls[0]["chat_id"] == "env-chat-77"


def test_partial_failure_records_errors(monkeypatch):
    """2nd chunk send raises -> sent=False, errors=[{chunk_idx:1,...}]."""
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    fake = _FakeTelegram(fail_indices=(1,))
    module = types.ModuleType("swarm.telegram_alerts")
    module.send = fake.send  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "swarm.telegram_alerts", module)

    # Three sections, each large enough to force 3 chunks.
    sections = [
        f"## Section {i}\n\n" + ("x" * 3500) for i in range(3)
    ]
    pulse = "\n\n".join(sections)
    result = ppt.deliver_to_telegram(pulse, chat_id="55", voice=False)

    assert result["sent"] is False
    assert result["chunks"] == 3
    assert len(result["errors"]) == 1
    assert result["errors"][0]["chunk_idx"] == 1
    assert "simulated failure" in result["errors"][0]["error"]


def test_voice_skipped_when_env_unset(monkeypatch, fake_telegram):
    """voice=True but env unset -> voice_attached=False, no audio path."""
    monkeypatch.delenv("MARGOT_VOICE_REPLY_ENABLED", raising=False)
    pulse = (
        "## Per-project pulse\n\nbody\n\n"
        "## Cross-portfolio synthesis\n\nthe synthesis prose"
    )
    result = ppt.deliver_to_telegram(pulse, chat_id="11", voice=True)
    assert result["sent"] is True
    assert result["voice_attached"] is False
    for call in fake_telegram.calls:
        assert "audio_path" not in call


def test_voice_attached_when_enabled(monkeypatch, fake_telegram, tmp_path):
    """env=1 + voice=True + synthesis present -> audio_path on last chunk."""
    monkeypatch.setenv("MARGOT_VOICE_REPLY_ENABLED", "1")

    audio_file = tmp_path / "synth.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")

    fake_voice = types.ModuleType("swarm.voice_compose")

    def _fake_compose(text, *, out_dir, filename_stem, max_chars=None):
        return text, audio_file

    fake_voice.compose_margot_voice_reply = _fake_compose  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "swarm.voice_compose", fake_voice)

    pulse = (
        "## pi-ceo\n\nproject body\n\n"
        "## Cross-portfolio synthesis\n\n"
        "Top risk: revenue concentration. Top action: ship MR."
    )
    result = ppt.deliver_to_telegram(
        pulse, chat_id="22", voice=True, repo_root=tmp_path,
    )
    assert result["sent"] is True
    assert result["voice_attached"] is True
    # Only the last chunk should carry the audio_path.
    last_call = fake_telegram.calls[-1]
    assert last_call.get("audio_path") == str(audio_file)
    for call in fake_telegram.calls[:-1]:
        assert "audio_path" not in call


def test_voice_compose_failure_falls_back_to_text(
    monkeypatch, fake_telegram, tmp_path,
):
    """voice_compose raising -> voice_attached=False but text still sends."""
    monkeypatch.setenv("MARGOT_VOICE_REPLY_ENABLED", "1")

    fake_voice = types.ModuleType("swarm.voice_compose")

    def _explode(text, *, out_dir, filename_stem, max_chars=None):
        raise RuntimeError("elevenlabs_down")

    fake_voice.compose_margot_voice_reply = _explode  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "swarm.voice_compose", fake_voice)

    pulse = "## Cross-portfolio synthesis\n\nshort synthesis body"
    result = ppt.deliver_to_telegram(
        pulse, chat_id="33", voice=True, repo_root=tmp_path,
    )
    assert result["sent"] is True
    assert result["voice_attached"] is False
    assert result["errors"] == []


def test_extract_synthesis_returns_section_body():
    pulse = (
        "## Other section\n\nirrelevant\n\n"
        "## Cross-portfolio synthesis\n\nthe body of synth\n\n"
        "## Trailing section\n\nstuff"
    )
    body = ppt._extract_synthesis(pulse)
    assert body is not None
    assert "the body of synth" in body
    assert "Trailing section" not in body


def test_extract_synthesis_returns_none_when_missing():
    assert ppt._extract_synthesis("## Something else\n\nbody") is None
