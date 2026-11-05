"""lane_state.py: the saved state the PC lane supervisor reads (UNI-3291)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesh"))
import lane_state  # noqa: E402

PY = sys.executable


def test_begin_writes_a_running_state_with_the_resume_command(tmp_path: Path) -> None:
    st = lane_state.begin(str(tmp_path), 4242, ["run.cmd", "--x"], "clone", "UNI-1")
    got = lane_state.load(str(tmp_path))
    assert got == st
    assert got["schema"] == "lane-state/1" and got["state"] == "running"
    assert got["pid"] == 4242 and got["step"] == "clone" and got["linear_id"] == "UNI-1"
    assert got["resume"] == {"argv": ["run.cmd", "--x"], "cwd": str(tmp_path)}
    assert got["attempts"] == 0 and got["steps_done"] == []
    assert not list(tmp_path.glob("*.tmp")), "the atomic write left its temp file behind"


@pytest.mark.parametrize("content", [None, "", "{not json", '{"schema": "other", "state": "running"}',
                                     '{"schema": "lane-state/1", "state": "sleeping"}', "[1, 2]"])
def test_load_refuses_a_missing_or_untrustworthy_file(tmp_path: Path, content) -> None:
    if content is not None:
        (tmp_path / "lane-state.json").write_text(content, encoding="utf-8")
    with pytest.raises(lane_state.StateError):
        lane_state.load(str(tmp_path))


def test_a_restart_keeps_finished_steps_attempts_and_history(tmp_path: Path) -> None:
    lane_state.begin(str(tmp_path), 1, ["a"], "one")
    lane_state.update(str(tmp_path), steps_done=["one"], attempts=2, history=[{"action": "resumed"}])
    first = lane_state.load(str(tmp_path))["created_epoch"]
    st = lane_state.begin(str(tmp_path), 2, ["a"], "two")
    assert st["pid"] == 2 and st["step"] == "two"
    assert st["steps_done"] == ["one"] and st["attempts"] == 2 and st["created_epoch"] == first
    assert st["history"] == [{"action": "resumed"}]


def test_a_fresh_begin_after_done_starts_clean(tmp_path: Path) -> None:
    lane_state.begin(str(tmp_path), 1, ["a"], "one")
    lane_state.update(str(tmp_path), state="done", steps_done=["one"], attempts=3)
    st = lane_state.begin(str(tmp_path), 2, ["a"])
    assert st["steps_done"] == [] and st["attempts"] == 0 and st["state"] == "running"


def _marker_cmd(marker: Path, rc: int = 0) -> list:
    return [PY, "-c", f"open(r'{marker}', 'a').write('x'); raise SystemExit({rc})"]


def test_run_step_checkpoints_first_and_never_redoes_a_finished_step(tmp_path: Path) -> None:
    lane_state.begin(str(tmp_path), 1, ["a"])
    marker = tmp_path / "ran.txt"
    assert lane_state.run_step(str(tmp_path), "codex-review", _marker_cmd(marker)) == 0
    st = lane_state.load(str(tmp_path))
    assert st["steps_done"] == ["codex-review"] and st["step"] == "codex-review"
    assert "step_started_epoch" in st
    assert lane_state.run_step(str(tmp_path), "codex-review", _marker_cmd(marker)) == 0
    assert marker.read_text() == "x", "a finished step ran a second time"


def test_a_failed_step_is_not_recorded_as_done(tmp_path: Path) -> None:
    lane_state.begin(str(tmp_path), 1, ["a"])
    marker = tmp_path / "ran.txt"
    assert lane_state.run_step(str(tmp_path), "receipt", _marker_cmd(marker, 3)) == 3
    assert lane_state.load(str(tmp_path))["steps_done"] == []
    assert lane_state.run_step(str(tmp_path), "receipt", _marker_cmd(marker, 0)) == 0
    assert marker.read_text() == "xx", "a failed step must run again on resume"


def test_cli_begin_finish_and_show(tmp_path: Path, capsys) -> None:
    d = str(tmp_path)
    assert lane_state.main(["begin", "--dir", d, "--pid", "77", "--step", "s1", "--linear", "UNI-9",
                            "--", "powershell.exe", "-File", "run.ps1"]) == 0
    assert json.loads(capsys.readouterr().out)["resume"]["argv"] == ["powershell.exe", "-File", "run.ps1"]
    assert lane_state.main(["finish", "--dir", d, "--state", "parked", "--note", "why"]) == 0
    assert lane_state.main(["show", "--dir", d]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["state"] == "parked" and shown["note"] == "why"


def test_cli_begin_without_a_command_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        lane_state.main(["begin", "--dir", str(tmp_path), "--pid", "5"])
    assert not (tmp_path / "lane-state.json").exists()
