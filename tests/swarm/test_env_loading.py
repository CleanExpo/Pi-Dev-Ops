"""
test_env_loading.py — verify scripts/start_swarm.sh loads env files
correctly at boot.

RA-1986 follow-up: Gemini research engine reads GEMINI_API_KEY from
~/.hermes/.env. Cron does not source shell rc files, so the launcher
script must source the hermes env explicitly. .env.local must still
win on conflict (it holds swarm-specific overrides like LINEAR_API_KEY).
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = REPO_ROOT / "scripts" / "start_swarm.sh"


def _run_launcher(tmp_path: Path, hermes_env: str | None, local_env: str) -> dict[str, str]:
    """Run start_swarm.sh with stubbed HOME + .env.local + stub python.

    Returns the env captured at the moment exec would have fired.
    The stub python prints its env and exits 0 instead of running the swarm.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    if hermes_env is not None:
        (fake_home / ".hermes").mkdir()
        (fake_home / ".hermes" / ".env").write_text(hermes_env)

    # Stub python: dump env then exit. We override the hard-coded pyenv path
    # by editing a temp copy of the launcher.
    stub_python = tmp_path / "stub-python"
    stub_python.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        env
    """))
    stub_python.chmod(0o755)

    # Copy launcher and patch the hard-coded paths for the test sandbox.
    launcher_src = START_SCRIPT.read_text()
    patched = launcher_src.replace(
        '/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.env.local',
        str(tmp_path / '.env.local'),
    ).replace(
        '/Users/phill-mac/.pyenv/versions/3.13.13/bin/python -m swarm.orchestrator',
        f'{stub_python}',
    )
    launcher_copy = tmp_path / "start_swarm.sh"
    launcher_copy.write_text(patched)
    launcher_copy.chmod(0o755)

    (tmp_path / ".env.local").write_text(local_env)

    result = subprocess.run(
        ["/bin/bash", str(launcher_copy)],
        env={"HOME": str(fake_home), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_hermes_env_keys_are_loaded(tmp_path):
    """GEMINI_API_KEY in ~/.hermes/.env reaches the swarm process env."""
    env = _run_launcher(
        tmp_path,
        hermes_env="GEMINI_API_KEY=hermes-gemini-key-123\n",
        local_env="LINEAR_API_KEY=local-linear-key\n",
    )
    assert env.get("GEMINI_API_KEY") == "hermes-gemini-key-123"
    assert env.get("LINEAR_API_KEY") == "local-linear-key"


def test_env_local_overrides_hermes_on_conflict(tmp_path):
    """Both files defining LINEAR_API_KEY: .env.local must win."""
    env = _run_launcher(
        tmp_path,
        hermes_env="LINEAR_API_KEY=hermes-loser\nGEMINI_API_KEY=gem\n",
        local_env="LINEAR_API_KEY=local-winner\n",
    )
    assert env.get("LINEAR_API_KEY") == "local-winner"
    # Non-conflicting hermes key still survives.
    assert env.get("GEMINI_API_KEY") == "gem"


def test_missing_hermes_env_is_non_fatal(tmp_path):
    """Launcher must not abort when ~/.hermes/.env is absent."""
    env = _run_launcher(
        tmp_path,
        hermes_env=None,
        local_env="LINEAR_API_KEY=local-only\n",
    )
    assert env.get("LINEAR_API_KEY") == "local-only"
    assert "GEMINI_API_KEY" not in env
