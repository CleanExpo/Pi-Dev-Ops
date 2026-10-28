"""RA-8127: a settings.json hook whose target file is missing must stay quiet, not error on every message.

On the Mac Mini sessions launch from the home directory, so $CLAUDE_PROJECT_DIR is ~ and the continuation-horizon
hook path points at ~/.claude/hooks, where no file exists; the senior-harness driver is a per-machine symlink the
Mini never got. Both printed an error on every prompt, tool call and stop. Phill chose to keep both OFF there, so a
missing target must mean "off, silently" -- and a present target must still run exactly as before.
"""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = ("continuation_horizon_hook.py", "run_setup_driver.sh")


def _commands() -> list[tuple[str, str]]:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [(event, hook["command"]) for event, groups in settings["hooks"].items() for group in groups
            for hook in group["hooks"] if any(t in hook["command"] for t in TARGETS)]


def _run(command: str, home: Path) -> subprocess.CompletedProcess:
    env = {"HOME": str(home), "CLAUDE_PROJECT_DIR": str(home), "PATH": "/usr/bin:/bin"}
    return subprocess.run(["/bin/bash", "-c", command], input="{}", capture_output=True, text=True, cwd=home,
                          env=env, timeout=60)


def test_every_guarded_hook_is_registered():
    events = sorted(event for event, _ in _commands())
    assert events == ["PreToolUse", "SessionStart", "Stop", "UserPromptSubmit", "UserPromptSubmit"], events


def test_a_missing_target_exits_zero_without_an_error(tmp_path):
    home = tmp_path / "home"
    (home / ".claude" / "hooks").mkdir(parents=True)
    for event, command in _commands():
        result = _run(command, home)
        assert result.returncode == 0, (event, command, result.stderr)
        assert result.stderr == "", (event, result.stderr)
        if event == "SessionStart":
            assert "senior-harness is not installed" in result.stdout, result.stdout
        else:
            assert result.stdout == "", (event, result.stdout)


def _plant_targets(home: Path, marker: Path) -> None:
    hooks = home / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "continuation_horizon_hook.py").write_text(
        f"import sys\nopen({str(marker)!r}, 'a').write('continuation\\n')\nsys.exit(3)\n")
    driver = home / ".claude" / "skills" / "senior-harness" / "scripts"
    driver.mkdir(parents=True)
    (driver / "run_setup_driver.sh").write_text(f'echo "driver $*" >> "{marker}"\nexit 5\n')


def test_a_present_target_still_runs_with_its_arguments_and_its_failure(tmp_path):
    home, marker = tmp_path / "home", tmp_path / "marker.txt"
    _plant_targets(home, marker)
    for event, command in _commands():
        marker.write_text("")
        result = _run(command, home)
        ran = marker.read_text()
        if "continuation_horizon_hook" in command:
            assert ran == "continuation\n", (event, ran)
            assert result.returncode == 1, (event, result.returncode)
        else:
            assert ran == f"driver hook --surface claude --event {event} --allow-non-git\n", (event, ran)
            assert result.returncode == 5, (event, result.returncode)
        assert "not installed" not in result.stdout
