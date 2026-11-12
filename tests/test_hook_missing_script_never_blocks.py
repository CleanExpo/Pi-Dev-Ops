"""RA-8340: no registered hook may block every tool call because its script is not in the project folder.

A session whose project folder is not this repository (a chat started in an app folder, then moved) runs every
hook in .claude/settings.json with $CLAUDE_PROJECT_DIR pointing at that folder. `python3 <missing file>` exits 2,
and for PreToolUse exit 2 means "block": every tool call was refused, including the ones needed to move the
session. It stopped a chat for over an hour on 12/11/2026.

The autonomy gate is a safety control, so "missing means off" is only half the answer: while ~/.claude/HARD_STOP
exists, a missing or crashing gate must still refuse the call, and stdout must then be exactly one JSON document
or Claude Code will not read the deny. Without HARD_STOP, the session is told the gate is off through
additionalContext, which reaches the model; stderr on exit 0 does not.
"""
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = "autonomy_gate_hook.py"
SHELLS = ["/bin/bash", "/bin/sh"]  # Claude Code may run hooks under either


def _hooks() -> list[tuple[str, str]]:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [(event, hook["command"]) for event, groups in settings["hooks"].items() for group in groups
            for hook in group["hooks"] if hook.get("type") == "command"]


def _gate_command() -> str:
    found = [command for event, command in _hooks() if GATE in command]
    assert len(found) == 1, found
    return found[0]


def _run(command: str, home: Path, project: Path, payload: str = "{}",
         shell: str = "/bin/bash") -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "CLAUDE_PROJECT_DIR": str(project), "PATH": "/usr/bin:/bin",
           "WORKTREE_DIR": str(project / "wt"), "WORKTREE_BRANCH": "ra-8340-probe",
           # stop `git -C <project>` in the worktree hooks from finding a repository above the temp folder
           "GIT_CEILING_DIRECTORIES": str(project.parent)}
    return subprocess.run([shell, "-c", command], input=payload, capture_output=True, text=True,
                          cwd=project, env=env, timeout=60)


def _bare(tmp_path: Path) -> tuple[Path, Path]:
    home, project = tmp_path / "home", tmp_path / "project"
    (home / ".claude" / "hooks").mkdir(parents=True)
    project.mkdir()
    return home, project


def _context(result: subprocess.CompletedProcess) -> str:
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out
    return out["additionalContext"]


def _deny_reason(result: subprocess.CompletedProcess) -> str:
    out = json.loads(result.stdout)["hookSpecificOutput"]  # exactly one JSON document
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


@pytest.mark.parametrize("shell", SHELLS)
def test_no_registered_hook_exits_2_when_nothing_is_installed(tmp_path, shell):
    """The class guard: every registration, present and future, is checked."""
    home, project = _bare(tmp_path)
    hooks = _hooks()
    assert len(hooks) >= 8, hooks  # a parse that found nothing would pass vacuously
    for event, command in hooks:
        result = _run(command, home, project, shell=shell)
        assert result.returncode != 2, (event, command, result.stderr)


@pytest.mark.parametrize("shell", SHELLS)
def test_missing_gate_without_hard_stop_allows_and_tells_the_session(tmp_path, shell):
    home, project = _bare(tmp_path)
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    context = _context(result)
    assert f"{project}/.claude/hooks/{GATE}" in context
    assert "RA-8340" in context


@pytest.mark.parametrize("shell", SHELLS)
def test_missing_gate_with_hard_stop_still_denies(tmp_path, shell):
    home, project = _bare(tmp_path)
    (home / ".claude" / "HARD_STOP").write_text("")
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    reason = _deny_reason(result)
    assert "HARD_STOP" in reason and "~/.claude/HARD_STOP is removed" in reason


def _plant(path: Path, marker: Path, code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import sys\nopen({str(marker)!r}, 'a').write(sys.stdin.read() + '\\n')\n"
                    f"print('gate-output')\nsys.exit({code})\n")


def test_project_copy_runs_and_its_output_is_passed_through(tmp_path):
    home, project = _bare(tmp_path)
    marker = tmp_path / "ran.txt"
    _plant(project / ".claude" / "hooks" / GATE, marker, 0)
    result = _run(_gate_command(), home, project, payload='{"tool_name": "Bash"}')
    assert result.returncode == 0, result.stderr
    assert result.stdout == "gate-output\n"
    assert marker.read_text() == '{"tool_name": "Bash"}\n'


def test_the_home_copy_is_never_run(tmp_path):
    """The home copy on the Mini is a stale pre-RA-8125 file; a missing project copy means off, not fallback."""
    home, project = _bare(tmp_path)
    marker = tmp_path / "home-ran.txt"
    _plant(home / ".claude" / "hooks" / GATE, marker, 0)
    result = _run(_gate_command(), home, project, payload='{"tool_name": "Read"}')
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert "RA-8340" in _context(result)


@pytest.mark.parametrize("shell", SHELLS)
def test_a_crashing_gate_never_exits_2_and_says_why(tmp_path, shell):
    home, project = _bare(tmp_path)
    _plant(project / ".claude" / "hooks" / GATE, tmp_path / "ran.txt", 2)
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    context = _context(result)  # the gate's own partial output is dropped
    assert f"{project}/.claude/hooks/{GATE} exited 2" in context


@pytest.mark.parametrize("shell", SHELLS)
def test_a_crashing_gate_under_hard_stop_prints_only_the_deny(tmp_path, shell):
    home, project = _bare(tmp_path)
    _plant(project / ".claude" / "hooks" / GATE, tmp_path / "ran.txt", 2)
    (home / ".claude" / "HARD_STOP").write_text("")
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    assert "HARD_STOP" in _deny_reason(result)
