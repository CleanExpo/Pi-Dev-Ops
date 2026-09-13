"""UNI-2644 — the mesh repo guard compares repositories, not URL spellings.

`canonical_origin` used to strip `.git` from http(s) only. HTTPS vs SSH of the
same repo still compared unequal, so a relocated Mini/PC clone was refused at
startup. These tests are the mutation control: restore that compare and the
SSH/HTTPS same-repo cases go red.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from mesh_helpers import load_module

HTTPS = "https://github.com/CleanExpo/Pi-Dev-Ops.git"
HTTPS_BARE = "https://github.com/CleanExpo/Pi-Dev-Ops"
SSH_SCP = "git@github.com:CleanExpo/Pi-Dev-Ops.git"
SSH_URL = "ssh://git@github.com/CleanExpo/Pi-Dev-Ops.git"
IDENTITY = "github.com/CleanExpo/Pi-Dev-Ops"


def _guard(name: str = "mesh_repo_guard_identity"):
    return load_module(name, "mesh/repo_guard.py")


def _repo_with_origin(path: Path, origin: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", origin],
        check=True, capture_output=True,
    )
    return path


def test_https_matches_ssh_scp_and_ssh_url():
    """MUTATION CONTROL. Old compare left these three unequal."""
    guard = _guard()
    got = {guard.canonical_origin(u) for u in (HTTPS, HTTPS_BARE, SSH_SCP, SSH_URL)}
    assert got == {IDENTITY}


def test_different_host_owner_or_repo_still_differs():
    guard = _guard("mesh_repo_guard_identity_diff")
    mine = guard.canonical_origin(HTTPS)
    assert guard.canonical_origin("https://github.com/other/thing.git") != mine
    assert guard.canonical_origin("git@github.com:CleanExpo/other.git") != mine
    assert guard.canonical_origin("https://gitlab.com/CleanExpo/Pi-Dev-Ops.git") != mine


def test_file_remote_keeps_dot_git_significant():
    guard = _guard("mesh_repo_guard_identity_file")
    assert guard.canonical_origin("file:///srv/expected") != (
        guard.canonical_origin("file:///srv/expected.git")
    )


def test_https_and_ssh_spellings_of_one_repository_are_accepted(tmp_path):
    """A relocated SSH clone of the HTTPS checkout must be allowed."""
    guard = _guard("mesh_repo_guard_identity_reloc")
    own = _repo_with_origin(tmp_path / "own", HTTPS)
    for label, origin in (("scp", SSH_SCP), ("ssh-url", SSH_URL), ("bare", HTTPS_BARE)):
        clone = _repo_with_origin(tmp_path / label, origin)
        assert guard.repo_dir_problem(clone, own) == "", origin


def test_different_repository_is_still_refused_across_protocols(tmp_path):
    guard = _guard("mesh_repo_guard_identity_refuse")
    own = _repo_with_origin(tmp_path / "own", HTTPS)
    foreign = _repo_with_origin(tmp_path / "foreign", "git@github.com:other/thing.git")
    problem = guard.repo_dir_problem(foreign, own)
    assert problem
    assert "other/thing" in problem


def test_git_origin_reads_local_url_not_insteadof(tmp_path, monkeypatch):
    """insteadOf must not mask a foreign origin as this repository."""
    guard = _guard("mesh_repo_guard_identity_instead")
    repo = _repo_with_origin(tmp_path / "foreign", "https://github.com/other/thing")
    cfg = tmp_path / "gitconfig"
    cfg.write_text(
        '[url "https://github.com/CleanExpo/Pi-Dev-Ops.git"]\n'
        "\tinsteadOf = https://github.com/other/thing\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    rewritten = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    stored = guard.git_origin(repo)
    assert stored == "https://github.com/other/thing"
    assert rewritten != stored
