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



# The privileged, network, service and package commands either script calls. Each stub
# only appends its argv to the log. Ordinary utilities (bash, nohup, cp, mkdir, cat)
# run for real, but only inside the temp HOME the scripts are given.
_STUBS = ("sudo", "pmset", "launchctl", "curl", "open", "ollama", "pgrep", "sleep",
          "tmux", "brew", "apt-get")


def _run_sandboxed(script: str, tmp_path) -> list[str]:
    """Run a repo shell script with a temp HOME and fake commands first on PATH."""
    from pathlib import Path  # noqa: PLC0415
    root = Path(__file__).resolve().parents[2]
    home, fake, log = tmp_path / "home", tmp_path / "bin", tmp_path / "calls.log"
    (home / "Library/LaunchAgents").mkdir(parents=True)  # present in any real macOS home
    fake.mkdir()
    for name in _STUBS:
        stub = fake / name
        # pmset -g feeds a grep in the setup script; give it a line to match.
        extra = 'if [ "$1" = "-g" ]; then echo " sleep 0"; fi\n' if name == "pmset" else ""
        # curl -o FILE must leave a file behind for the installer's chmod/cp.
        extra += ('out=""; prev=""; for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done; '
                  '[ -n "$out" ] && : > "$out"\n') if name == "curl" else ""
        rc = "1" if name == "pgrep" else "0"
        # A slow backgrounded `ollama serve` makes the race below certain rather than rare,
        # so dropping the wait fails here every time, not one CI run in many.
        delay = '[ "$1" = serve ] && /bin/sleep 1\n' if name == "ollama" else ""
        stub.write_text(f'#!/bin/sh\n{delay}echo "{name} $*" >> "{log}"\n{extra}exit {rc}\n')
        stub.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{fake}:/usr/bin:/bin", "TERM": "dumb"}
    rc, out = _run_and_wait_for_descendants(["/bin/bash", str(root / script)], env, tmp_path)
    assert rc == 0, out
    return log.read_text().splitlines() if log.exists() else []


def _run_and_wait_for_descendants(cmd: list[str], env: dict, cwd, timeout: float = 60.0):
    """Run cmd, then wait for every process it left behind, all within one deadline.

    The installer backgrounds `ollama serve`, so the script can exit before that stub has
    logged (main CI, 82096e66). Every descendant inherits this pipe's write end, so EOF on
    the read end means every one of them has closed it. A holder that outlives the deadline
    has its whole process group killed and fails the test (Codex review of c2b39b9a).
    """
    import os  # noqa: PLC0415
    import select  # noqa: PLC0415
    import signal  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import time  # noqa: PLC0415
    deadline = time.monotonic() + timeout
    done_r, done_w = os.pipe()
    with os.fdopen(done_r, "rb") as done:
        try:
            proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    pass_fds=(done_w,), start_new_session=True)
        finally:
            os.close(done_w)
        try:
            out, _ = proc.communicate(timeout=max(0.0, deadline - time.monotonic()))
            # Small reads, deadline checked every pass: a holder writing to or flooding the
            # pipe must not outlast it (Codex reviews of ae351130 and 697c9201).
            while True:
                remaining = deadline - time.monotonic()
                ready = remaining > 0 and select.select([done], [], [], remaining)[0]
                if not ready:
                    raise TimeoutError(f"a descendant of {cmd} still held the pipe after {timeout}s")
                if not os.read(done.fileno(), 4096):
                    break
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):  # group already empty
                pass
            proc.wait()
    return proc.returncode, out


def test_watchdog_setup_still_loads_the_ollama_relaunch_agent(tmp_path):
    """RA-638 must survive stage 1: the swarm still runs on Ollama (Codex review of
    10309ddd: a text match passed with the load line commented out)."""
    calls = _run_sandboxed("scripts/setup_ra637_ra638.sh", tmp_path)
    plist = tmp_path / "home/Library/LaunchAgents/com.piceo.ollama-watchdog.plist"
    assert f"launchctl load {plist}" in calls
    assert plist.exists()


def test_installer_still_pulls_the_supervisor_model(tmp_path):
    calls = _run_sandboxed("scripts/supervisor/install-on-new-machine.sh", tmp_path)
    assert "ollama pull mistral" in calls
    assert "ollama serve" in calls
