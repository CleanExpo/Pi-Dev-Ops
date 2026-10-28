"""RA-8125: the autonomy-ladder PreToolUse gate must run however it is reached.

On the Mac Mini sessions start from the home directory, so $CLAUDE_PROJECT_DIR is not the repo, and the hook is
reached through ~/.claude/hooks/autonomy_gate_hook.py, a symlink. The hook used abspath to find its repo, could
not import swarm, and every tool call ran with the L3 deny and the HARD_STOP kill switch silently off.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "autonomy_gate_hook.py"
PAYLOAD = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})


def _home(tmp_path: Path, hard_stop: bool) -> Path:
    home = tmp_path / "home"
    (home / ".claude" / "hooks").mkdir(parents=True)
    if hard_stop:
        (home / ".claude" / "HARD_STOP").write_text("test\n")
    return home


def _run(args: list[str], home: Path, cwd: Path, project_dir: Path) -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
           "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run(args, input=PAYLOAD, capture_output=True, text=True, cwd=cwd, env=env, timeout=60)


def _decision(result: subprocess.CompletedProcess) -> str | None:
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_the_hook_reached_through_a_symlink_from_outside_the_repo_still_gates(tmp_path):
    for hard_stop, expected in ((True, "deny"), (False, None)):
        home = _home(tmp_path / str(hard_stop), hard_stop)
        link = home / ".claude" / "hooks" / "autonomy_gate_hook.py"
        link.symlink_to(HOOK)
        assert _decision(_run([sys.executable, str(link)], home, home, home)) == expected


def test_the_settings_command_runs_the_trusted_hook_never_one_from_the_cwd_repo(tmp_path):
    """Codex round 1: the hook must come from the launch dir's install (the Mini's ~/.claude/hooks link), never
    from whichever git repository the session is standing in, or that repo's file replaces the gate."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]
                if "autonomy_gate_hook.py" in h["command"]]
    assert len(commands) == 1, commands
    home = _home(tmp_path, hard_stop=True)
    (home / ".claude" / "hooks" / "autonomy_gate_hook.py").symlink_to(HOOK)
    foreign = tmp_path / "foreign"
    (foreign / ".claude" / "hooks").mkdir(parents=True)
    (foreign / ".claude" / "hooks" / "autonomy_gate_hook.py").write_text("print('FOREIGN_HOOK_SELECTED')\n")
    subprocess.run(["git", "init", "-q", str(foreign)], check=True)
    python_dir = Path(sys.executable).parent
    command = commands[0].replace("python3 ", f"{python_dir}/python3 ", 1) if (python_dir / "python3").exists() \
        else commands[0]
    result = _run(["/bin/bash", "-c", command], home, foreign, home)
    assert "FOREIGN_HOOK_SELECTED" not in result.stdout
    assert _decision(result) == "deny"
