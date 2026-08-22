"""Prove the shipped Senior Harness slice, not a test-local reconstruction of it.

Every assertion here reads the literal checked-in artefact: the hook commands are
executed exactly as the manifests spell them, the installer is the vendored file,
and the skill documents are scanned for the executables they instruct.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills"
VENDORED_SKILLS = ("senior-harness", "model-router", "unlazy")
INSTALLER = SKILL_ROOT / "senior-harness" / "scripts" / "install_senior_harness.sh"
MANIFESTS = (
    (Path(".claude") / "settings.json", "claude"),
    (Path(".codex") / "hooks.json", "codex"),
)


def _shipped_setup_driver_hooks() -> list[dict[str, str]]:
    """Read every checked-in setup_driver hook command byte-for-byte."""
    hooks: list[dict[str, str]] = []
    for relative, surface in MANIFESTS:
        manifest = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
        for event, groups in manifest["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    command = hook["command"]
                    if "run_setup_driver.sh" in command:
                        hooks.append(
                            {
                                "manifest": relative.as_posix(),
                                "surface": surface,
                                "event": event,
                                "command": command,
                            }
                        )
    return hooks


def _install_root(tmp_path: Path) -> Path:
    """A HOME whose skill roots resolve exactly the way the shipped commands assume."""
    home = tmp_path / "home"
    for host in (".claude", ".codex"):
        skills = home / host / "skills"
        skills.mkdir(parents=True)
        for skill in VENDORED_SKILLS:
            (skills / skill).symlink_to(SKILL_ROOT / skill)
    return home


def _hook_env(tmp_path: Path, home: Path) -> dict[str, str]:
    """Pin the interpreter and the state roots without touching the command string.

    The manifests spell `python3`, so `python3` is what has to run. A shim first on
    PATH makes that name resolve to the interpreter running this test instead of
    whatever the host happens to ship, leaving the command itself unmodified.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return dict(
        os.environ,
        HOME=str(home),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        SENIOR_HARNESS_STATE_DIR=str(tmp_path / "state"),
        SENIOR_HARNESS_SEAL_KEY_FILE=str(tmp_path / "seal.key"),
    )


def _run_shipped(command: str, *, env: dict[str, str], cwd: Path, payload: dict) -> dict:
    result = subprocess.run(
        ["/bin/sh", "-c", command],
        input=json.dumps(payload),
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{command}\nstdout={result.stdout}\nstderr={result.stderr}"
    return json.loads(result.stdout)


def test_shipped_hook_manifests_declare_the_full_recovery_command_set() -> None:
    hooks = _shipped_setup_driver_hooks()
    assert len(hooks) == 6, hooks
    covered = {(hook["surface"], hook["event"]) for hook in hooks}
    assert covered == {
        (surface, event)
        for surface in ("claude", "codex")
        for event in ("SessionStart", "UserPromptSubmit", "PreToolUse")
    }
    for hook in hooks:
        assert f"--surface {hook['surface']}" in hook["command"], hook
        assert f"--event {hook['event']}" in hook["command"], hook
        # The flag is the whole point: without it main() denies the first
        # outside-Git prompt instead of freezing it.
        assert "--allow-non-git" in hook["command"], hook


def _start_outside_git(command: str, env: dict[str, str], outside: Path, session: str) -> None:
    started = _run_shipped(
        command,
        env=env,
        cwd=outside,
        payload={"session_id": session, "cwd": str(outside), "hook_event_name": "SessionStart"},
    )
    assert "permissionDecision" not in started["hookSpecificOutput"]


def _enter_git(command: str, env: dict[str, str], session: str) -> str:
    entered = _run_shipped(
        command,
        env=env,
        cwd=REPO_ROOT,
        payload={
            "session_id": session,
            "cwd": str(REPO_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {},
        },
    )
    assert "permissionDecision" not in entered["hookSpecificOutput"]
    return entered["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("surface", ["claude", "codex"])
def test_shipped_hook_commands_recover_an_outside_git_prompt_unmodified(
    tmp_path: Path, surface: str
) -> None:
    hooks = {
        hook["event"]: hook["command"]
        for hook in _shipped_setup_driver_hooks()
        if hook["surface"] == surface
    }
    home = _install_root(tmp_path)
    env = _hook_env(tmp_path, home)
    outside = tmp_path / "outside-git"
    outside.mkdir()
    session = f"shipped-{surface}"
    prompt = "Recover the harness from outside a Git checkout"

    _start_outside_git(hooks["SessionStart"], env, outside, session)
    frozen = _run_shipped(
        hooks["UserPromptSubmit"],
        env=env,
        cwd=outside,
        payload={
            "session_id": session,
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        },
    )
    assert repr(prompt) in frozen["hookSpecificOutput"]["additionalContext"]
    pending = list((tmp_path / "state" / "pending-project").glob("*.json"))
    assert len(pending) == 1, pending

    context = _enter_git(hooks["PreToolUse"], env, session)
    assert "recovered pending objective" in context
    assert repr(prompt) in context


@pytest.mark.parametrize("surface", ["claude", "codex"])
def test_dropping_the_shipped_flag_loses_the_outside_git_prompt(
    tmp_path: Path, surface: str
) -> None:
    """Negative control: the passing test above must depend on the shipped flag."""
    command = next(
        hook["command"]
        for hook in _shipped_setup_driver_hooks()
        if hook["surface"] == surface and hook["event"] == "UserPromptSubmit"
    )
    stripped = command.replace(" --allow-non-git", "")
    assert stripped != command
    home = _install_root(tmp_path)
    env = _hook_env(tmp_path, home)
    outside = tmp_path / "outside-git"
    outside.mkdir()

    rejected = _run_shipped(
        stripped,
        env=env,
        cwd=outside,
        payload={
            "session_id": f"stripped-{surface}",
            "cwd": str(outside),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Recover the harness from outside a Git checkout",
        },
    )
    assert "rejected hook input" in json.dumps(rejected)
    assert not list((tmp_path / "state").rglob("*.json"))


def _run_installer(home: Path, *args: str, repo: Path | None = None) -> subprocess.CompletedProcess:
    installer = (repo or REPO_ROOT) / "skills" / "senior-harness" / "scripts" / "install_senior_harness.sh"
    return subprocess.run(
        ["bash", str(installer), *args],
        env=dict(os.environ, HOME=str(home)),
        capture_output=True,
        text=True,
    )


def test_installer_dry_run_reports_the_plan_and_changes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _run_installer(home, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("LINK    ") == 10, result.stdout
    assert not list(home.iterdir())

def test_installer_links_every_skill_root_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = _run_installer(home)
    assert first.returncode == 0, first.stderr
    for host in (".codex", ".claude", ".agents"):
        for skill in VENDORED_SKILLS:
            link = home / host / "skills" / skill
            assert link.is_symlink()
            assert Path(os.readlink(link)) == SKILL_ROOT / skill
            assert (link / "SKILL.md").is_file()

    second = _run_installer(home)
    assert second.returncode == 0, second.stderr
    assert second.stdout.count("CURRENT ") == 10, second.stdout
    assert "LINK    " not in second.stdout


def test_installer_relinks_a_stale_skill_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    stale_target = tmp_path / "stale-senior-harness"
    stale_target.mkdir()
    (home / ".codex" / "skills").mkdir(parents=True)
    (home / ".codex" / "skills" / "senior-harness").symlink_to(stale_target)

    result = _run_installer(home)
    assert result.returncode == 0, result.stderr
    assert "UPDATE  " in result.stdout
    assert Path(os.readlink(home / ".codex" / "skills" / "senior-harness")) == (
        SKILL_ROOT / "senior-harness"
    )


def test_installer_refuses_a_real_directory_before_touching_any_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    protected = home / ".agents" / "skills" / "unlazy"
    protected.mkdir(parents=True)
    (protected / "SKILL.md").write_text("real user content\n", encoding="utf-8")

    result = _run_installer(home)
    assert result.returncode == 3, result.stdout
    assert "refusing to replace real path" in result.stderr
    assert (protected / "SKILL.md").read_text(encoding="utf-8") == "real user content\n"
    assert not (home / ".codex").exists()
    assert not (home / ".claude").exists()


def test_installer_refuses_an_incomplete_source_tree(tmp_path: Path) -> None:
    fake_repo = tmp_path / "fake-repo"
    for skill in ("senior-harness", "model-router"):
        (fake_repo / "skills" / skill).mkdir(parents=True)
        (fake_repo / "skills" / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\n---\n", encoding="utf-8"
        )
    scripts = fake_repo / "skills" / "senior-harness" / "scripts"
    scripts.mkdir()
    shutil.copy2(INSTALLER, scripts / INSTALLER.name)
    home = tmp_path / "home"
    home.mkdir()

    result = _run_installer(home, repo=fake_repo)
    assert result.returncode == 2, result.stdout
    assert "required source skill is missing" in result.stderr
    assert not list(home.iterdir())
