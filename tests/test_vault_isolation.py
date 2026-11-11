"""UNI-3351: no test may reach the machine's real 2nd Brain vault or its Obsidian REST bridge.

These tests guard the autouse fixture `_isolated_brain_vault` in tests/conftest.py. They
fail when that fixture is removed, on any machine, because the settings then point at the
home folder and the default bridge address instead of this test's own temporary folder.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from swarm import analyst, config

REAL_BRIDGE_PORT = 27124


def _assert_settings_are_isolated(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    for name in ("BRAIN1_WIKI_DIR", "OBSIDIAN_VAULT"):
        value = Path(getattr(config, name)).resolve()
        assert value.is_relative_to(root), f"swarm.config.{name} escapes the test folder: {value}"
    assert config.OBSIDIAN_REMOTE_URL == "", "a remote Obsidian bridge is configured"
    bridge = urlsplit(config.OBSIDIAN_BASE_URL)
    assert bridge.hostname == "127.0.0.1", f"Obsidian bridge is not loopback: {bridge.hostname}"
    assert bridge.port != REAL_BRIDGE_PORT, "Obsidian bridge is the real local REST port"


def test_vault_settings_point_inside_this_tests_own_folder(tmp_path):
    _assert_settings_are_isolated(tmp_path)


def test_analyst_note_and_mirror_land_inside_the_test_folder(tmp_path, monkeypatch):
    # Checked first, so a missing fixture fails here before anything is written.
    _assert_settings_are_isolated(tmp_path)

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
