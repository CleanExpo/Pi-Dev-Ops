"""run_setup_driver.sh must find a 3.10+ interpreter installed under a versioned name.

On a Mac, `python3` on PATH is Apple's /usr/bin/python3 (3.9.6) while 3.11 to 3.14 are
installed only as python3.11 ... python3.14. The launcher probed SENIOR_HARNESS_PYTHON,
the checkout's .venv and bare `python3`, then failed closed with "Python 3.10 or newer is
unavailable" on a machine holding four compatible interpreters (28/11/2026). Every Claude
lifecycle hook that runs the launcher exits 2 in that case, and a UserPromptSubmit hook
exiting 2 blocks the prompt. The launcher now probes the versioned names, newest first,
after bare `python3`.

The tests build a PATH of fake interpreters, so they behave the same on a Mac with only 3.9
and on CI with only 3.11. A fake answers the launcher's version probe and otherwise prints
which one was chosen. The checkout's own .venv is hidden from the launcher by running a copy
of it from a temp dir three levels deep, so `../../../.venv` resolves to nothing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "skills" / "senior-harness" / "scripts" / "run_setup_driver.sh"


def _write_shim(directory: Path, name: str, minor: int) -> None:
    ok = "printf 'senior-harness-python-ok\\n'; " if minor >= 10 else ""
    directory.joinpath(name).write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-c" ]; then ' + ok + "exit 0; fi\n"
        f"printf 'CHOSEN={name}\\n'\n",
        encoding="utf-8",
    )
    directory.joinpath(name).chmod(0o755)


def _isolated_launcher(tmp_path: Path) -> Path:
    """A copy of the launcher where `$script_dir/../../../.venv` does not exist."""
    scripts = tmp_path / "root" / "skills" / "senior-harness" / "scripts"
    scripts.mkdir(parents=True)
    target = scripts / "run_setup_driver.sh"
    shutil.copy2(LAUNCHER, target)
    return target


PROBED_NAMES = ("python3", "python3.14", "python3.13", "python3.12", "python3.11", "python3.10")


def _run(tmp_path: Path, pythons: dict[str, int]) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Every name the launcher probes gets a shim, incompatible (3.9) unless the test says
    # otherwise. PATH keeps /usr/bin for sh utilities, so without this a real
    # /usr/bin/python3.12 (Ubuntu 24.04) would be found before the shims and the
    # fail-closed and python3.10 cases would pass or fail for the wrong reason.
    for name in PROBED_NAMES:
        _write_shim(bin_dir, name, pythons.get(name, 9))
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
    # `status` is neither `hook` nor `contract`, so the launcher execs
    # setup_driver.py through the chosen interpreter; the shim prints CHOSEN instead.
    return subprocess.run(
        ["sh", str(_isolated_launcher(tmp_path)), "status"],
        env=env, capture_output=True, text=True, timeout=30,
    )


def test_versioned_python_is_found_when_bare_python3_is_too_old(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3": 9, "python3.12": 12})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3.12" in result.stdout


def test_newest_versioned_interpreter_wins(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3": 9, "python3.11": 11, "python3.14": 14})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3.14" in result.stdout


def test_bare_python3_still_preferred_when_compatible(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3": 12, "python3.14": 14})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3\n" in result.stdout


def test_shim_list_covers_every_name_the_launcher_probes() -> None:
    """If python3.15 is added to the launcher's loop without updating PROBED_NAMES, a real
    /usr/bin/python3.15 could be reached ahead of the shims and the tests above would lie."""
    loops = re.findall(r"^\s*for candidate in (.+); do$", LAUNCHER.read_text(encoding="utf-8"), re.M)
    assert len(loops) == 1, loops
    launcher_names = set(loops[0].split())
    assert launcher_names, "launcher probes no versioned names"
    assert launcher_names | {"python3"} == set(PROBED_NAMES)


def test_still_fails_closed_when_nothing_compatible_exists(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3": 9})
    assert result.returncode == 2
    assert "Python 3.10 or newer is unavailable" in result.stderr


@pytest.mark.parametrize("name", ["python3.10", "python3.13"])
def test_every_probed_versioned_name_is_accepted(tmp_path: Path, name: str) -> None:
    result = _run(tmp_path, {"python3": 9, name: int(name.split(".")[1])})
    assert result.returncode == 0, result.stderr
    assert f"CHOSEN={name}" in result.stdout
