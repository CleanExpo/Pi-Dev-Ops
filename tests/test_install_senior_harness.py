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


# Pi-Dev-Ops owns senior-harness, model-router and unlazy. A skill root that is itself a Git
# checkout (on a real machine, ~/.claude is the skills-library repo) must ignore every one of
# those slots, or the next pull of that checkout can re-vendor, overwrite or delete what the
# installer placed there. These guards fail if that shadowing can come back.
OWNED_SKILLS = ("senior-harness", "model-router", "unlazy")


def _skill_library_checkout(home: Path) -> Path:
    checkout = home / ".claude"
    git_repo(checkout)
    return checkout


def _git(checkout: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True
    ).stdout


def _no_installed_slots(home: Path) -> bool:
    return not any(
        (home / host / "skills" / skill).is_symlink()
        for host in (".codex", ".claude", ".agents")
        for skill in OWNED_SKILLS
    )


def test_installer_refuses_a_slot_that_a_skill_library_checkout_tracks(tmp_path: Path) -> None:
    # The shape found on the MacBook on 28/11/2026: senior-harness ignored, the other two
    # tracked as real directories.
    checkout = _skill_library_checkout(tmp_path)
    (checkout / ".gitignore").write_text("skills/senior-harness\n", encoding="utf-8")
    for skill in ("model-router", "unlazy"):
        copy = checkout / "skills" / skill / "SKILL.md"
        copy.parent.mkdir(parents=True)
        copy.write_text(f"---\nname: {skill}\n---\nforked copy\n", encoding="utf-8")
    _git(checkout, "add", ".gitignore", "skills")
    _git(checkout, "commit", "-qm", "vendor copies")
    tracked = checkout / "skills" / "model-router" / "SKILL.md"

    result = subprocess.run(
        ["bash", str(INSTALLER), "--dry-run"],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert f"tracked by the git checkout at {checkout.resolve()}" in result.stderr
    assert "skills/model-router" in result.stderr
    assert tracked.read_text(encoding="utf-8").endswith("forked copy\n")
    assert _no_installed_slots(tmp_path)


def test_installer_refuses_a_slot_its_git_checkout_does_not_ignore(tmp_path: Path) -> None:
    checkout = _skill_library_checkout(tmp_path)

    result = subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert f"the git checkout at {checkout.resolve()} does not ignore it" in result.stderr
    assert _no_installed_slots(tmp_path)
    assert not (checkout / "skills").exists()


def test_installer_links_into_a_checkout_that_ignores_every_slot_and_leaves_it_clean(
    tmp_path: Path,
) -> None:
    checkout = _skill_library_checkout(tmp_path)
    (checkout / ".gitignore").write_text(
        "".join(f"skills/{skill}\n" for skill in OWNED_SKILLS), encoding="utf-8"
    )
    _git(checkout, "add", ".gitignore")
    _git(checkout, "commit", "-qm", "ignore the harness-owned slots")

    subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    for skill in OWNED_SKILLS:
        installed = checkout / "skills" / skill
        assert installed.is_symlink()
        assert installed.resolve() == (REPO_ROOT / "skills" / skill).resolve()
    assert _git(checkout, "status", "--porcelain", "--untracked-files=all") == ""


def _git_refusing_rev_parse(bin_dir: Path) -> None:
    # Git's dubious-ownership refusal (a checkout owned by another user with no
    # safe.directory exception) cannot be produced by one test user, so a shim
    # reproduces its exact exit code and message for rev-parse and delegates the rest.
    real_git = subprocess.run(
        ["/bin/sh", "-c", "command -v git"], check=True, capture_output=True, text=True
    ).stdout.strip()
    bin_dir.mkdir(parents=True)
    shim = bin_dir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = rev-parse ]; then\n'
        "    echo \"fatal: detected dubious ownership in repository at '$PWD'\" >&2\n"
        "    exit 128\n"
        "  fi\n"
        "done\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)


def test_installer_refuses_when_git_cannot_inspect_an_enclosing_checkout(
    tmp_path: Path,
) -> None:
    # CodeRabbit on PR 1039: a Git inspection error must not read as "outside every
    # checkout", or the tracked and ignored checks are skipped and a tracked slot is
    # replaced.
    checkout = _skill_library_checkout(tmp_path)
    fake_bin = tmp_path / "bin"
    _git_refusing_rev_parse(fake_bin)

    result = subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path), PATH=f"{fake_bin}:{os.environ['PATH']}"),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3, result.stderr
    assert "cannot be checked" in result.stderr
    assert _no_installed_slots(tmp_path)
    assert not (checkout / "skills").exists()


def test_installer_still_links_slots_outside_every_checkout_when_rev_parse_fails(
    tmp_path: Path,
) -> None:
    # The other side of the same guard: with no .git above a slot, a failing
    # rev-parse means "no checkout", and installation proceeds.
    fake_bin = tmp_path / "bin"
    _git_refusing_rev_parse(fake_bin)

    subprocess.run(
        ["bash", str(INSTALLER)],
        env=dict(os.environ, HOME=str(tmp_path), PATH=f"{fake_bin}:{os.environ['PATH']}"),
        check=True,
        capture_output=True,
        text=True,
    )

    assert not _no_installed_slots(tmp_path)
