"""run_setup_driver.sh must find a 3.10+ interpreter installed under a versioned name.

On a Mac, `python3` on PATH is Apple's /usr/bin/python3 (3.9.6) while 3.11 to 3.14 are
installed only as python3.11 ... python3.14. The launcher probed SENIOR_HARNESS_PYTHON,
the checkout's .venv and bare `python3`, then failed closed with "Python 3.10 or newer is
unavailable" on a machine holding four compatible interpreters (28/11/2026, RA-8662).
Every Claude lifecycle hook that runs the launcher exits 2 in that case, and a
UserPromptSubmit hook exiting 2 blocks the prompt. The launcher now probes the versioned
names, newest first, after bare `python3`.

Every probed name is faked through tests/_launcher_python_shims.py, which reads the names
from the launcher, so the tests behave the same on a Mac with only 3.9 and on Ubuntu CI
with a real /usr/bin/python3.12. The checkout's own .venv is hidden from the launcher by
running a copy of it from a temp dir three levels deep, so `../../../.venv` resolves to
nothing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from _launcher_python_shims import LAUNCHER, probed_versioned_names, write_python_shims

TESTS_DIR = Path(__file__).resolve().parent


def _isolated_launcher(tmp_path: Path) -> Path:
    """A copy of the launcher where `$script_dir/../../../.venv` does not exist."""
    scripts = tmp_path / "root" / "skills" / "senior-harness" / "scripts"
    scripts.mkdir(parents=True)
    target = scripts / "run_setup_driver.sh"
    shutil.copy2(LAUNCHER, target)
    return target


def _run(tmp_path: Path, compatible: dict[str, int]) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    write_python_shims(bin_dir, compatible)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}
    # `status` is neither `hook` nor `contract`, so the launcher execs
    # setup_driver.py through the chosen interpreter; the shim prints CHOSEN instead.
    return subprocess.run(
        ["sh", str(_isolated_launcher(tmp_path)), "status"],
        env=env, capture_output=True, text=True, timeout=30,
    )


def test_versioned_python_is_found_when_bare_python3_is_too_old(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3.12": 12})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3.12" in result.stdout


def test_newest_versioned_interpreter_wins(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3.11": 11, "python3.14": 14})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3.14" in result.stdout


def test_bare_python3_still_preferred_when_compatible(tmp_path: Path) -> None:
    result = _run(tmp_path, {"python3": 12, "python3.14": 14})
    assert result.returncode == 0, result.stderr
    assert "CHOSEN=python3\n" in result.stdout


def test_still_fails_closed_when_nothing_compatible_exists(tmp_path: Path) -> None:
    result = _run(tmp_path, {})
    assert result.returncode == 2
    assert "Python 3.10 or newer is unavailable" in result.stderr


@pytest.mark.parametrize("name", probed_versioned_names())
def test_every_probed_versioned_name_is_accepted(tmp_path: Path, name: str) -> None:
    result = _run(tmp_path, {name: int(name.split(".")[1])})
    assert result.returncode == 0, result.stderr
    assert f"CHOSEN={name}" in result.stdout


def test_shims_cover_every_interpreter_name_the_launcher_mentions() -> None:
    """A second probing mechanism (another loop, a literal `python3.15`) would not be read
    by the helper, so a real interpreter of that name could leak into every test."""
    mentioned = set(re.findall(r"\bpython3\.\d+\b", LAUNCHER.read_text(encoding="utf-8")))
    assert mentioned, "launcher names no versioned interpreter"
    assert mentioned == set(probed_versioned_names())


def test_every_launcher_test_with_system_dirs_on_path_uses_the_shared_shims() -> None:
    """The class guard. Twice a test faked only `python3` while /usr/bin stayed on PATH,
    so on Ubuntu CI the launcher found the real /usr/bin/python3.12 and the test measured
    the host. Any test that runs the launcher with /usr/bin on PATH must shadow every
    probed name through write_python_shims."""
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        runs_launcher = "run_setup_driver" in text or "RUNNER" in text
        if runs_launcher and ":/usr/bin" in text and "write_python_shims" not in text:
            offenders.append(path.name)
    assert offenders == [], offenders
