"""Stage 1 of the Ollama removal must not blind the swarm (21/10/2026).

Founder ruling: remove Ollama entirely, in stages. Stage 1 moves Margot's casual chat to
free OpenRouter only. The swarm bots (builder, scribe, guardian's own analysis) still call
swarm.ollama_client until stage 2, so the swarm pre-flight and Guardian must still report a
down Ollama backend instead of "ready". A Codex review of 6231afc4 found both silent.
"""
from __future__ import annotations

from unittest import mock

from swarm import health_check
from swarm.bots import guardian


def test_preflight_fails_when_ollama_is_down(capsys):
    with mock.patch("swarm.ollama_client.list_models", return_value=[]), \
         mock.patch("swarm.telegram_alerts.send", return_value=True):
        assert health_check.run() is False
    assert "Ollama not reachable" in capsys.readouterr().out


def test_preflight_passes_when_ollama_and_models_are_up():
    from swarm import config
    models = sorted(set(config.BOT_MODELS.values()))
    with mock.patch("swarm.ollama_client.list_models", return_value=models), \
         mock.patch("swarm.ollama_client.health_check", return_value=True), \
         mock.patch("swarm.telegram_alerts.send", return_value=True):
        assert health_check.run() is True


def test_guardian_pages_critical_on_a_confirmed_ollama_outage(tmp_path, monkeypatch):
    monkeypatch.setattr(guardian.config, "SWARM_LOG_DIR", tmp_path)
    monkeypatch.setattr(guardian, "list_models", lambda: [])
    monkeypatch.setattr(guardian, "chat", lambda *a, **k: "")
    sent: list[dict] = []
    monkeypatch.setattr(guardian, "send", lambda **k: sent.append(k) or True)
    results = [guardian.run_cycle(0) for _ in range(guardian.OLLAMA_DOWN_CONFIRM_STREAK)]
    assert results[-1]["severity"] == "critical"
    # The page itself, not just the classification (Codex review of ead70313).
    pages = [k for k in sent if k.get("severity") == "critical"]
    assert len(pages) == 1
    assert "Ollama not responding" in pages[0]["message"]


def test_ollama_recovery_and_install_stay_until_stage_two():
    """The RA-638 relaunch watchdog and the supervisor's Ollama install must survive
    stage 1: the swarm and supervisor still run on Ollama (Codex review of ead70313)."""
    from pathlib import Path  # noqa: PLC0415
    root = Path(__file__).resolve().parents[2]
    setup = (root / "scripts/setup_ra637_ra638.sh").read_text()
    assert "com.piceo.ollama-watchdog" in setup
    assert "launchctl load ~/Library/LaunchAgents/com.piceo.ollama-watchdog.plist" in setup
    installer = (root / "scripts/supervisor/install-on-new-machine.sh").read_text()
    assert "ollama pull mistral" in installer
