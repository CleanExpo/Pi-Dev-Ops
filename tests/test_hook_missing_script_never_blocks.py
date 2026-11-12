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
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = "autonomy_gate_hook.py"
# Claude Code may run hooks under any of these. /bin/sh is bash on macOS and dash on Ubuntu (GitHub CI), so dash
# runs here too wherever it is installed, to see locally what CI sees.
SHELLS = ["/bin/bash", "/bin/sh"] + (["/bin/dash"] if Path("/bin/dash").exists() else [])


def _hooks() -> list[tuple[str, str]]:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [(event, hook["command"]) for event, groups in settings["hooks"].items() for group in groups
            for hook in group["hooks"] if hook.get("type") == "command"]


def _gate_command() -> str:
    found = [command for event, command in _hooks() if GATE in command]
    assert len(found) == 1, found
    return found[0]


def _run(command: str, home: Path, project: Path, payload: str = "{}", shell: str = "/bin/bash",
         path: str = "/usr/bin:/bin") -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "CLAUDE_PROJECT_DIR": str(project), "PATH": path,
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
    assert f"no $CLAUDE_PROJECT_DIR/.claude/hooks/{GATE}" in context  # constant text: nothing interpolated
    assert "RA-8340" in context
    assert f"no copy at {project}/.claude/hooks/{GATE}" in result.stderr  # the expanded path goes to stderr


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


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("out", ["", '{"a":1}', '{"a":1}\n', '{"a":1}\n\n', "\n\n", ' {"a": "x\n"} \n\n\n'])
def test_a_successful_gate_output_reaches_claude_code_byte_for_byte(tmp_path, shell, out):
    """Codex round 5: `$(...)` drops trailing newlines, so capturing the output changed it. Before RA-8340 the gate
    wrote straight to Claude Code; on exit 0 the line must hand over the same bytes (NUL bytes aside, see the
    named-limit test below)."""
    home, project = _bare(tmp_path)
    gate = project / ".claude" / "hooks" / GATE
    gate.parent.mkdir(parents=True)
    gate.write_text(f"import sys\nsys.stdin.read()\nsys.stdout.write({out!r})\n")
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    assert result.stdout == out


@pytest.mark.parametrize("shell", SHELLS)
def test_named_limit_a_nul_byte_in_gate_output_is_dropped(tmp_path, shell):
    """Named limit, pinned so a change is noticed: a shell variable cannot hold a NUL byte, so the relay drops it.
    The real gate writes json.dumps output, which never contains one."""
    home, project = _bare(tmp_path)
    gate = project / ".claude" / "hooks" / GATE
    gate.parent.mkdir(parents=True)
    gate.write_text("import sys\nsys.stdin.read()\nsys.stdout.buffer.write(b'{\"a\":1}\\x00\\n')\n")
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    assert result.stdout == '{"a":1}\n'


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
    assert "ran but failed" in context and "RA-8340" in context
    assert f"{project}/.claude/hooks/{GATE} exited 2" in result.stderr


def _silent(path: Path, code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"import sys\nsys.stdin.read()\nsys.exit({code})\n")


def _real(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(REPO / ".claude" / "hooks" / GATE)


# Every way the gate can behave. Codex round 1 found the real gate returns 0 with no output on input it cannot
# parse, before it reads HARD_STOP, so the settings line must not rely on the gate for the kill switch at all.
GATE_KINDS = {
    "missing": lambda project, tmp: None,
    "silent-allow": lambda project, tmp: _silent(project / ".claude" / "hooks" / GATE, 0),
    "prints-then-allows": lambda project, tmp: _plant(project / ".claude" / "hooks" / GATE, tmp / "ran.txt", 0),
    "crashes": lambda project, tmp: _plant(project / ".claude" / "hooks" / GATE, tmp / "ran.txt", 2),
    "real-gate": lambda project, tmp: _real(project / ".claude" / "hooks" / GATE),
}


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("kind", sorted(GATE_KINDS))
@pytest.mark.parametrize("payload", ["{", '{"tool_name": "Read", "tool_input": {"file_path": "/x"}}'])
def test_hard_stop_denies_whatever_the_gate_does(tmp_path, shell, kind, payload):
    home, project = _bare(tmp_path)
    GATE_KINDS[kind](project, tmp_path)
    (home / ".claude" / "HARD_STOP").write_text("")
    result = _run(_gate_command(), home, project, payload=payload, shell=shell,
                  path=f"{Path(sys.executable).parent}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    reason = _deny_reason(result)  # stdout is exactly one JSON document: the deny
    assert "HARD_STOP" in reason and "~/.claude/HARD_STOP is removed" in reason


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("kind", ["missing", "prints-then-allows"])
def test_without_python3_the_session_is_still_told_the_gate_is_off(tmp_path, shell, kind):
    """Codex round 2: with no python3 the gate cannot run and the encoder could not either, so nothing was printed.
    Every stdout path the line writes itself must be a constant that needs shell builtins alone."""
    home, project = _bare(tmp_path)
    GATE_KINDS[kind](project, tmp_path)
    result = _run(_gate_command(), home, project, shell=shell, path=str(tmp_path / "no-such-bin"))
    assert result.returncode == 0, result.stderr
    context = _context(result)
    assert "autonomy gate is off" in context and "RA-8340" in context


@pytest.mark.parametrize("shell", SHELLS)
def test_hard_stop_denies_without_python3(tmp_path, shell):
    home, project = _bare(tmp_path)
    (home / ".claude" / "HARD_STOP").write_text("")
    result = _run(_gate_command(), home, project, shell=shell, path=str(tmp_path / "no-such-bin"))
    assert result.returncode == 0, result.stderr
    assert "~/.claude/HARD_STOP is removed" in _deny_reason(result)


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("code", [None, 2])
def test_the_notice_is_valid_json_for_any_project_path(tmp_path, shell, code):
    """Codex round 1: the path was pasted into the JSON by printf, so a quote in a folder name broke it."""
    home = tmp_path / "home"
    (home / ".claude" / "hooks").mkdir(parents=True)
    project = tmp_path / 'my "quoted" pro\\ject\tx'
    project.mkdir()
    if code is not None:
        _plant(project / ".claude" / "hooks" / GATE, tmp_path / "ran.txt", code)
    result = _run(_gate_command(), home, project, shell=shell)
    assert result.returncode == 0, result.stderr
    assert "RA-8340" in _context(result)
    assert f"{project}/.claude/hooks/{GATE}" in result.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_a_broken_python3_cannot_corrupt_the_notice(tmp_path, shell):
    """Codex round 3: a python3 that prints garbage and exits 0 turned the round-3 notice into `not-json`. The line
    writes only constants itself, so no interpreter can change what it prints."""
    home, project = _bare(tmp_path)
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "python3").write_text("#!/bin/sh\necho not-json\n")
    (shim / "python3").chmod(0o755)
    result = _run(_gate_command(), home, project, shell=shell, path=f"{shim}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    assert "RA-8340" in _context(result)


@pytest.mark.parametrize("shell", SHELLS)
def test_hard_stop_is_found_under_a_home_with_spaces(tmp_path, shell):
    """A HOME containing a space still finds the marker. The unset-HOME case is the next test."""
    home, project = tmp_path / "my home", tmp_path / "project"
    (home / ".claude").mkdir(parents=True)
    project.mkdir()
    _silent(project / ".claude" / "hooks" / GATE, 0)
    (home / ".claude" / "HARD_STOP").write_text("")
    result = _run(_gate_command(), home, project, payload="{", shell=shell)
    assert result.returncode == 0, result.stderr
    assert "~/.claude/HARD_STOP is removed" in _deny_reason(result)


@pytest.mark.parametrize("shell", ["/bin/bash"])
def test_with_home_unset_the_line_checks_the_same_hard_stop_as_the_gate(tmp_path, shell):
    """With HOME unset the gate's expanduser falls back to the account's home folder. `$HOME/...` would look at
    /.claude/HARD_STOP instead, so a kill switch set there would be missed. The marker cannot be planted in the real
    home (it stops every agent), so this reads the shell's own trace of the path the line tests; nothing is created.
    Bash only, a named limit: dash leaves a bare `~` unexpanded when HOME is unset, so under dash neither `~` nor
    `$HOME` finds the marker. Claude Code always sets HOME for hooks."""
    project = tmp_path / "project"
    project.mkdir()
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(project), "GIT_CEILING_DIRECTORIES": str(tmp_path)}
    gate_looks_at = subprocess.run(
        [sys.executable, "-c", "import os; print(os.path.expanduser('~/.claude/HARD_STOP'))"],
        capture_output=True, text=True, env=env, check=True).stdout.strip()
    assert gate_looks_at.startswith("/") and gate_looks_at != "/.claude/HARD_STOP", gate_looks_at
    result = subprocess.run([shell, "-x", "-c", _gate_command()], input="{}", capture_output=True, text=True,
                            cwd=project, env=env, timeout=60)
    assert result.returncode == 0, result.stderr
    checks = [line for line in result.stderr.splitlines() if line.startswith("+") and "HARD_STOP" in line]
    assert checks and gate_looks_at in checks[0], (gate_looks_at, checks)


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("payload", ["", "{", "[]", "null", '{"tool_name": 5}',
                                     '{"tool_name": "Read", "tool_input": {"file_path": "/x"}}',
                                     '{"tool_name": "mcp__supabase__apply_migration", "tool_input": {}}'])
def test_the_real_gate_prints_nothing_or_one_json_object(tmp_path, shell, payload):
    """Named limit: when the gate exits 0 its stdout passes through unchecked, exactly as before RA-8340, so the gate
    owns that output. This checks the owner: whatever it is fed, it prints nothing (allow) or one JSON object."""
    home, project = _bare(tmp_path)
    _real(project / ".claude" / "hooks" / GATE)
    result = _run(_gate_command(), home, project, payload=payload, shell=shell,
                  path=f"{Path(sys.executable).parent}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    if result.stdout.strip():
        assert isinstance(json.loads(result.stdout), dict), result.stdout
