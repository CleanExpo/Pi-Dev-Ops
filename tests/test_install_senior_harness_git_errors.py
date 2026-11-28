"""The installer when Git itself cannot inspect a slot's enclosing checkout.

Split from test_install_senior_harness.py to keep both under the 300-line file
convention (.github/scripts/file_length_lint.py)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from test_install_senior_harness import INSTALLER, _no_installed_slots, _skill_library_checkout


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
