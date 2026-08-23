"""Security controls for Grill session-state publication."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "senior-harness" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import grill_session  # noqa: E402


def test_state_write_does_not_follow_the_legacy_predictable_temp_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path))
    state_path = tmp_path / "session.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("do not overwrite", encoding="utf-8")
    legacy_temp = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    legacy_temp.symlink_to(victim)

    grill_session._write_state(state_path, {"objective": "private"})

    assert victim.read_text(encoding="utf-8") == "do not overwrite"
    assert legacy_temp.is_symlink(), "an unrelated colliding path must remain untouched"
    assert not state_path.is_symlink()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {"objective": "private"}


def test_state_write_publishes_mode_0600_even_over_a_permissive_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path))
    state_path = tmp_path / "session.json"
    state_path.write_text("old state", encoding="utf-8")
    state_path.chmod(0o644)

    grill_session._write_state(state_path, {"answer_verbatim": "confidential"})

    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "answer_verbatim": "confidential"
    }


def test_state_write_refuses_a_symlinked_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(tmp_path))
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(OSError):
        grill_session._write_state(linked_parent / "session.json", {"private": True})
    assert not (real_parent / "session.json").exists()


def test_state_control_directories_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "control"
    monkeypatch.setenv("SENIOR_HARNESS_STATE_DIR", str(root))
    state_path = root / "project" / "session.json"
    grill_session._write_state(state_path, {"private": True})
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700
