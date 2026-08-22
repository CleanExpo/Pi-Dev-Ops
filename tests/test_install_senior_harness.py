from __future__ import annotations

import os
import subprocess
from pathlib import Path

from _harness_entry_support import git_repo


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "skills" / "senior-harness" / "scripts" / "install_senior_harness.sh"
ENTRY = REPO_ROOT / "scripts" / "pi-ceo-harness"


def test_installer_aligns_three_skill_roots_to_one_control_stack(tmp_path: Path) -> None:
    environment = dict(os.environ, HOME=str(tmp_path))
    subprocess.run(["bash", str(INSTALLER)], check=True, env=environment, capture_output=True, text=True)

    for host in (".codex", ".claude", ".agents"):
        for skill in ("senior-harness", "model-router", "unlazy"):
            installed = tmp_path / host / "skills" / skill
            assert installed.is_symlink()
            assert installed.resolve() == (REPO_ROOT / "skills" / skill).resolve()
    entry = tmp_path / ".local" / "bin" / "pi-ceo-harness"
    assert entry.is_symlink()
    assert entry.resolve() == ENTRY.resolve()


def test_installer_refuses_to_replace_a_real_skill_directory(tmp_path: Path) -> None:
    protected = tmp_path / ".agents" / "skills" / "senior-harness"
    protected.mkdir(parents=True)
    (protected / "SKILL.md").write_text("local control\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert "refusing to replace real path" in result.stderr
    assert (protected / "SKILL.md").read_text(encoding="utf-8") == "local control\n"
    assert not (tmp_path / ".codex" / "skills" / "senior-harness").exists()
    assert not (tmp_path / ".claude" / "skills" / "senior-harness").exists()


def test_entry_only_installer_does_not_retarget_skill_roots(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(INSTALLER), "--entry-only"],
        env=dict(os.environ, HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "entry launcher installed" in result.stdout
    entry = tmp_path / ".local" / "bin" / "pi-ceo-harness"
    assert entry.is_symlink()
    assert entry.resolve() == ENTRY.resolve()
    for host in (".codex", ".claude", ".agents"):
        assert not (tmp_path / host / "skills").exists()


def test_entry_launcher_resolves_a_real_checkout_from_any_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "Pi-Dev-Ops"
    git_repo(repo)
    outside = tmp_path / "outside"
    outside.mkdir()

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo), "--check"],
        cwd=outside,
        env=dict(os.environ, HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"worktree={repo}" in result.stdout
    assert "ENTRY_READY" in result.stdout


def test_entry_launcher_recovers_the_legacy_wrapper_to_the_real_repo(tmp_path: Path) -> None:
    repo = tmp_path / "Pi-Dev-Ops"
    git_repo(repo)
    wrapper = tmp_path / "Pi-CEO" / "Pi-Dev-Ops"
    wrapper.mkdir(parents=True)

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(wrapper), "--check"],
        env=dict(os.environ, HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ENTRY_RECOVERED" in result.stderr
    assert f"worktree={repo}" in result.stdout


def test_entry_launcher_recovers_a_normalised_legacy_wrapper_path(tmp_path: Path) -> None:
    repo = tmp_path / "Pi-Dev-Ops"
    git_repo(repo)
    wrapper = tmp_path / "Pi-CEO" / "Pi-Dev-Ops"
    wrapper.mkdir(parents=True)

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", f"{wrapper}/", "--check"],
        env=dict(os.environ, HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ENTRY_RECOVERED" in result.stderr
    assert f"worktree={repo}" in result.stdout


def test_entry_launcher_rejects_an_unregistered_non_git_path(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(outside), "--check"],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ENTRY_BLOCKED" in result.stderr
    assert "not_a_git_checkout" in result.stderr


def test_entry_launcher_rejects_ambiguous_repo_and_worktree_flags(tmp_path: Path) -> None:
    repo = tmp_path / "Pi-Dev-Ops"
    git_repo(repo)

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo), "--worktree", str(repo), "--check"],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ambiguous_target" in result.stderr
