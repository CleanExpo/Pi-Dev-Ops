"""Adversarial coverage for the Senior Harness entry launcher."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from _harness_entry_support import git_repo


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "scripts" / "pi-ceo-harness"


def test_launcher_ignores_ambient_git_context_for_non_git_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    git_repo(repo)
    outside.mkdir()
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        GIT_DIR=str(repo / ".git"),
        GIT_WORK_TREE=str(repo),
        GIT_COMMON_DIR="/definitely/missing/git-common",
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(outside), "--check"],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "not_a_git_checkout" in result.stderr
    assert "ENTRY_READY" not in result.stdout


def test_launcher_ignores_ambient_git_common_dir_for_valid_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    git_repo(repo)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        GIT_COMMON_DIR="/definitely/missing/git-common",
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo), "--check"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ENTRY_READY" in result.stdout
    assert f"worktree={repo}" in result.stdout


def test_launcher_ignores_legacy_wrapper_environment_override(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    git_repo(repo)
    outside.mkdir()
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PI_CEO_REPO_ROOT=str(repo),
        PI_CEO_LEGACY_WRAPPER=str(outside),
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(outside), "--check"],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ENTRY_RECOVERED" not in result.stderr
    assert "not_a_git_checkout" in result.stderr


def test_launcher_does_not_claim_recovery_for_invalid_default(tmp_path: Path) -> None:
    wrapper = tmp_path / "Pi-CEO" / "Pi-Dev-Ops"
    wrapper.mkdir(parents=True)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PI_CEO_REPO_ROOT=str(tmp_path / "missing-default"),
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(wrapper), "--check"],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ENTRY_RECOVERED" not in result.stderr
    assert "not_a_git_checkout" in result.stderr


def test_launcher_blocks_before_ready_when_host_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    git_repo(repo)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PI_CEO_CLAUDE_BIN=str(tmp_path / "missing-claude"),
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo)],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "claude_not_found" in result.stderr
    assert "ENTRY_READY" not in result.stdout


def test_launcher_blocks_before_ready_when_host_is_a_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fake_host = tmp_path / "host-directory"
    git_repo(repo)
    fake_host.mkdir()
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PI_CEO_CLAUDE_BIN=str(fake_host),
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo)],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "claude_not_found" in result.stderr
    assert "ENTRY_READY" not in result.stdout


def test_launcher_absolutizes_host_from_relative_path_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    fake_bin = tmp_path / "bin"
    hostile_cdpath = tmp_path / "hostile" / "bin"
    receipt = tmp_path / "receipt"
    git_repo(repo)
    fake_bin.mkdir()
    hostile_cdpath.mkdir(parents=True)
    fake_host = fake_bin / "claude"
    fake_host.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$PWD" > "$HARNESS_RECEIPT"\n',
        encoding="utf-8",
    )
    fake_host.chmod(0o755)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        PATH=f"bin:{os.environ['PATH']}",
        CDPATH=str(hostile_cdpath.parent),
        HARNESS_RECEIPT=str(receipt),
    )

    result = subprocess.run(
        ["bash", str(ENTRY), "--repo", str(repo)],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "ENTRY_READY" in result.stdout
    assert receipt.read_text(encoding="utf-8") == f"{repo}\n"


@pytest.mark.parametrize(
    ("host_args", "binary_variable", "expected_host"),
    [([], "PI_CEO_CLAUDE_BIN", "claude"), (["--host", "codex"], "PI_CEO_CODEX_BIN", "codex")],
)
def test_launcher_executes_selected_host_with_literal_arguments(
    tmp_path: Path,
    host_args: list[str],
    binary_variable: str,
    expected_host: str,
) -> None:
    repo = tmp_path / "repo"
    receipt = tmp_path / "receipt"
    fake_host = tmp_path / "fake-host"
    git_repo(repo)
    fake_host.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$PWD" > "$HARNESS_RECEIPT"\nprintf "<%s>\\n" "$@" >> "$HARNESS_RECEIPT"\n',
        encoding="utf-8",
    )
    fake_host.chmod(0o755)
    environment = dict(
        os.environ,
        HOME=str(tmp_path),
        HARNESS_RECEIPT=str(receipt),
        **{binary_variable: str(fake_host)},
    )
    command = ["bash", str(ENTRY), "--repo", str(repo), *host_args, "--", "--name", "value with spaces"]

    result = subprocess.run(command, env=environment, check=True, capture_output=True, text=True)

    assert f"host={expected_host}" in result.stdout
    assert receipt.read_text(encoding="utf-8").splitlines() == [str(repo), "<--name>", "<value with spaces>"]
