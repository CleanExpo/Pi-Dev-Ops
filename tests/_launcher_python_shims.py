"""One owner for faking the interpreters run_setup_driver.sh can choose (RA-8662).

The launcher picks the first 3.10+ interpreter from SENIOR_HARNESS_PYTHON, the checkout's
.venv, bare `python3`, then a loop of versioned names. A test that fakes only `python3`
and keeps /usr/bin on PATH is not hermetic: on Ubuntu 24.04 /usr/bin/python3.12 is real,
so the loop finds it and the test measures the CI host instead of the launcher. That
defect reached review twice, in two different files, which is why the list of names is
read from the launcher here instead of being copied into each test.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "skills" / "senior-harness" / "scripts" / "run_setup_driver.sh"

_LOOP = re.compile(r"^\s*for candidate in (.+); do$", re.M)


def probed_versioned_names() -> tuple[str, ...]:
    """The versioned interpreter names the launcher's loop probes, in probe order."""
    loops = _LOOP.findall(LAUNCHER.read_text(encoding="utf-8"))
    if len(loops) != 1:
        raise AssertionError(f"expected one candidate loop in {LAUNCHER}, found {loops!r}")
    names = tuple(loops[0].split())
    if not names:
        raise AssertionError(f"candidate loop in {LAUNCHER} names no interpreter")
    return names


def probed_names() -> tuple[str, ...]:
    """Every PATH name the launcher may select: bare python3, then the versioned loop."""
    return ("python3", *probed_versioned_names())


def write_python_shims(bin_dir: Path, compatible: dict[str, int] | None = None) -> None:
    """Shadow every name the launcher probes with a fake in `bin_dir`.

    A name in `compatible` maps to its minor version (3.<minor>); any other name is an
    incompatible 3.9. A compatible fake answers the launcher's `-c` version probe with the
    marker; every fake, when executed for real, prints `CHOSEN=<name>` and exits 0.
    `bin_dir` must come first on PATH.
    """
    compatible = compatible or {}
    unknown = set(compatible) - set(probed_names())
    if unknown:
        raise AssertionError(f"launcher never probes {sorted(unknown)}")
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in probed_names():
        ok = "printf 'senior-harness-python-ok\\n'; " if compatible.get(name, 9) >= 10 else ""
        shim = bin_dir / name
        shim.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-c" ]; then ' + ok + "exit 0; fi\n"
            f"printf 'CHOSEN={name}\\n'\n",
            encoding="utf-8",
        )
        shim.chmod(0o755)
