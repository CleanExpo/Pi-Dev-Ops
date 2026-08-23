"""Installer rollback and vendored-script contract checks."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills"
VENDORED_SKILLS = ("senior-harness", "model-router", "unlazy")
INSTALLER = SKILL_ROOT / "senior-harness" / "scripts" / "install_senior_harness.sh"
RUNNER = SKILL_ROOT / "senior-harness" / "scripts" / "run_setup_driver.sh"


def _run_installer(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER)],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_installer_rolls_back_every_link_when_a_later_root_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    blocked = home / ".agents" / "skills"
    blocked.mkdir(parents=True)
    blocked.chmod(0o500)
    try:
        result = _run_installer(home)
        assert result.returncode != 0, result.stdout
        assert "previous skill links were restored" in result.stderr
        for host in (".codex", ".claude"):
            for skill in VENDORED_SKILLS:
                assert not (home / host / "skills" / skill).exists()
    finally:
        blocked.chmod(0o700)


def _instructed_executables() -> set[tuple[str, str]]:
    pattern = re.compile(r"[~$\w./-]*scripts/[\w.-]+\.(?:py|sh|mjs|js)")
    found: set[tuple[str, str]] = set()
    for skill in VENDORED_SKILLS:
        for document in sorted((SKILL_ROOT / skill).rglob("*.md")):
            for token in pattern.findall(document.read_text(encoding="utf-8")):
                found.add((skill, token))
    return found


def _resolve_instruction(skill: str, token: str) -> Path:
    relative = token
    for prefix in ("~/.codex/skills/", "~/.claude/skills/", "~/.agents/skills/"):
        if relative.startswith(prefix):
            relative = "skills/" + relative[len(prefix) :]
            break
    return SKILL_ROOT / skill / relative if relative.startswith("scripts/") else REPO_ROOT / relative


def test_every_script_the_vendored_skills_instruct_is_present() -> None:
    instructed = _instructed_executables()
    assert instructed, "expected the vendored skills to instruct at least one script"
    missing = [
        f"{skill}: {token} -> {_resolve_instruction(skill, token)}"
        for skill, token in sorted(instructed)
        if not _resolve_instruction(skill, token).is_file()
    ]
    assert not missing, "vendored skills instruct scripts that do not exist: " + "; ".join(missing)


def test_vendored_unlazy_skill_claims_no_runner_it_does_not_ship() -> None:
    text = (SKILL_ROOT / "unlazy" / "SKILL.md").read_text(encoding="utf-8")
    schema = (SKILL_ROOT / "unlazy" / "references" / "plan-contract-schema.md").read_text(
        encoding="utf-8"
    )
    for document in (text, schema):
        assert "python scripts/unlazy_plan.py" not in document
        assert "node scripts/unlazy-gate-check.mjs" not in document
    assert "ships **no** plan linter" in text or "no** plan linter" in text


@pytest.mark.parametrize("event", ["UserPromptSubmit", "PreToolUse"])
def test_hook_runner_fails_closed_without_a_compatible_python(tmp_path: Path, event: str) -> None:
    scripts = tmp_path / "skill" / "scripts"
    scripts.mkdir(parents=True)
    runner = scripts / RUNNER.name
    runner.write_bytes(RUNNER.read_bytes())
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python = fake_bin / "python3"
    python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    python.chmod(0o755)

    result = subprocess.run(
        ["bash", str(runner), "hook", "--event", event],
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Senior Harness denied execution" in result.stdout
    expected = '"decision":"block"' if event == "UserPromptSubmit" else '"permissionDecision":"deny"'
    assert expected in result.stdout
