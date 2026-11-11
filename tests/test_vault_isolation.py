"""UNI-3351: no test may reach the machine's real 2nd Brain vault or its Obsidian REST bridge.

These tests guard the autouse fixture `_isolated_brain_vault` in tests/conftest.py. They
fail when that fixture is removed, on any machine, because the settings then point at the
home folder and the default bridge address instead of this test's own temporary folder.

swarm.config caches its settings at import, so the fixture is checked in both orders: with
the module already imported (the usual case in a full run), and with the module first
imported inside the test (a fresh pytest process running only the two in-process tests).
Nothing in this file imports swarm at module level, so the second order is real.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BRIDGE_PORT = 27124
# Set only by the fresh-process tests below: the in-process tests then also prove that
# nothing (the fixture included) imported swarm.config before the test body ran.
FIRST_IMPORT_FLAG = "VAULT_ISOLATION_EXPECT_FIRST_IMPORT"
IN_PROCESS_TESTS = [
    "tests/test_vault_isolation.py::test_vault_settings_point_inside_this_tests_own_folder",
    "tests/test_vault_isolation.py::test_analyst_note_and_mirror_land_inside_the_test_folder",
]


def _isolated_config(tmp_path: Path):
    if os.environ.get(FIRST_IMPORT_FLAG):
        assert "swarm.config" not in sys.modules, (
            "swarm.config was imported before the test body: a fixture forced the first import")
    from swarm import config

    root = tmp_path.resolve()
    for name in ("BRAIN1_WIKI_DIR", "OBSIDIAN_VAULT"):
        value = Path(getattr(config, name)).resolve()
        assert value.is_relative_to(root), f"swarm.config.{name} escapes the test folder: {value}"
    assert config.OBSIDIAN_REMOTE_URL == "", "a remote Obsidian bridge is configured"
    bridge = urlsplit(config.OBSIDIAN_BASE_URL)
    assert bridge.hostname == "127.0.0.1", f"Obsidian bridge is not loopback: {bridge.hostname}"
    assert bridge.port != REAL_BRIDGE_PORT, "Obsidian bridge is the real local REST port"
    return config


def test_vault_settings_point_inside_this_tests_own_folder(tmp_path):
    _isolated_config(tmp_path)


def test_analyst_note_and_mirror_land_inside_the_test_folder(tmp_path, monkeypatch):
    # Checked first, so a missing fixture fails here before anything is written.
    config = _isolated_config(tmp_path)
    from swarm import analyst

    def _no_network(*args, **kwargs):
        raise AssertionError("the analyst tried to call the Obsidian REST bridge")

    monkeypatch.setattr(analyst.urllib.request, "urlopen", _no_network)
    monkeypatch.setattr(config, "OBSIDIAN_TOKEN", "test-token")

    deliverable = analyst._deterministic_deliverable("vault isolation guard", "A finding.", [])
    rel_path = analyst._write_analyst_note(deliverable, repo_root=tmp_path / "repo")

    wiki_note = Path(config.BRAIN1_WIKI_DIR) / rel_path
    mirror_note = Path(config.OBSIDIAN_VAULT) / "Wiki" / rel_path
    assert wiki_note.is_file()
    assert mirror_note.is_file()
    assert wiki_note.resolve().is_relative_to(tmp_path.resolve())
    assert mirror_note.resolve().is_relative_to(tmp_path.resolve())


def _fresh_pytest(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run pytest in a new process, so swarm.config has not been imported yet."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *args],
        cwd=REPO_ROOT, env={**os.environ, **env}, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.parametrize("node_id", IN_PROCESS_TESTS)
def test_first_import_inside_a_test_is_isolated_even_in_a_hostile_environment(node_id, tmp_path):
    """The outer environment names a vault and two bridges; the first import must see none.

    One test per fresh process, so each one really is the first importer.
    """
    outside = tmp_path / "outside"
    result = _fresh_pytest([node_id], {
        FIRST_IMPORT_FLAG: "1",
        "BRAIN1_WIKI_DIR": str(outside / "Wiki"),
        "OBSIDIAN_VAULT": str(outside),
        "OBSIDIAN_REMOTE_URL": "https://bridge.invalid:27124",
        "OBSIDIAN_URL": f"https://127.0.0.1:{REAL_BRIDGE_PORT}",
        "BRAIN_HOST_TAILNET": "brain-host.invalid",
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout, result.stdout
    assert not outside.exists(), "a test wrote into the folder the outer environment named"


def test_fixture_does_not_freeze_settings_ahead_of_a_tests_own_environment():
    """The regression this fixture once caused.

    tests/test_analyst.py sets TAO_ANALYST_ENABLED=1 in its own fixture and relies on
    swarm.config being imported after that. A fixture that imports the module first caches
    the outer value, and three analyst tests fail.
    """
    result = _fresh_pytest(["tests/test_analyst.py"], {"TAO_ANALYST_ENABLED": "0"})
    assert result.returncode == 0, result.stdout + result.stderr
