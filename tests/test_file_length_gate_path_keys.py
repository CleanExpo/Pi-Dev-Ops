"""Regression tests for the path keys `.github/scripts/file_length_lint.py` builds.

Found 2026-09-07 on Windows. `main` keyed its measurements with `str(Path(p))`,
which renders the PLATFORM separator. On Windows every key came out as
``app\\server\\session_phases.py`` while `.github/file-length.baseline.txt`
stores ``app/server/session_phases.py``. Every baseline lookup therefore missed.

Why it survived: on a clean tree the gate still passed. An unedited file matches
its baseline row by CONTENT FINGERPRINT, so all 182 baselined files were
forgiven as "moved" and the run ended green behind a wall of warnings. Edit one
of them and the fingerprint changes, the forgiveness stops, and the file is
reported as a brand-new 1969-line offender instead of one that grew by 41 lines.

That is a wrong verdict in the dangerous direction, twice over. It hides how big
the change actually was, and the remedy the failure message recommends --
``--update`` -- rewrites all 201 rows with backslash paths when run here, which
breaks the gate for every Linux CI runner that reads the same file.

PLATFORM NOTE, stated rather than hidden: this defect can only exist where
``os.sep != "/"``. These tests fail on Windows before the fix and pass after it.
On Linux they pass either way, so on Linux they are a vacuous green leg and
prove nothing. That is a property of the bug, not a weakness of the tests.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / ".github" / "scripts" / "file_length_lint.py"


def _load():
    """Import the script by path -- `.github/scripts` is not an importable package."""
    spec = importlib.util.spec_from_file_location("file_length_lint", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def test_key_is_posix_regardless_of_platform():
    """The key for a nested path uses forward slashes on every platform.

    `Path("app") / "server"` renders with a backslash under `str()` on Windows,
    so this assertion is the defect itself, expressed in one line.
    """
    assert gate._key(Path("app") / "server" / "session_phases.py") == (
        "app/server/session_phases.py"
    )


def test_no_baselined_path_looks_missing_from_the_real_tree():
    """Every path in the real baseline is found in the real measured tree.

    This is the end-to-end leg: it uses the checked-in baseline file and the
    repo's own tracked files, so it fails if the keying diverges in any way, not
    only via the separator. Before the fix this reported all 182 baselined files
    as absent, which is what turned every one of them into a "moved" warning.
    """
    tracked = subprocess.run(
        ["git", "ls-files", *gate.SUFFIXES],
        capture_output=True, text=True, check=True, cwd=_REPO,
    ).stdout.split("\n")
    measured = {gate._key(Path(p)) for p in tracked if p}

    baseline = gate.read_baseline()
    assert baseline, "baseline file is empty -- this control would pass vacuously"

    missing = sorted(p for p in baseline if p not in measured)
    assert missing == [], (
        f"{len(missing)} baselined path(s) do not match any measured key; "
        f"first three: {missing[:3]}"
    )


def test_the_missing_check_can_actually_report_a_missing_path():
    """Positive control for the test above.

    Without this, a keying bug that emptied `measured` would make the previous
    test fail loudly, but a bug that emptied `baseline` would make it pass
    silently. This proves the comparison reports absence when absence is real.
    """
    measured = {"app/server/session_phases.py"}
    baseline = {"app/server/session_phases.py": (1928, "d294b7b0d24b"),
                "app/server/deleted_module.py": (400, "ffffffffffff")}

    missing = sorted(p for p in baseline if p not in measured)
    assert missing == ["app/server/deleted_module.py"]


def test_written_baseline_has_no_carriage_returns(tmp_path, monkeypatch):
    """`--update` must not rewrite the whole file just by changing line endings.

    `write_baseline` called `Path.write_text(..., encoding="utf-8")` with no
    `newline` argument. Python's text mode then translates every "\n" to
    "\r\n" on Windows, so running `--update` here rewrote all 201 rows as CRLF
    while their content stayed byte-identical. The diff read as "201 insertions,
    201 deletions" and looked like a wholesale baseline rewrite, which is why an
    earlier session refused to run the update at all and recorded the blocker as
    unresolvable. The churn was line endings, not content.

    Same platform note as the tests above: real on Windows, vacuous on Linux.
    """
    target = tmp_path / "file-length.baseline.txt"
    monkeypatch.setattr(gate, "BASELINE_PATH", target)

    gate.write_baseline({
        "app/server/session_phases.py": (1969, "aaaaaaaaaaaa"),
        "swarm/margot_bot.py": (1770, "bbbbbbbbbbbb"),
        "app/server/small.py": (10, "cccccccccccc"),
    })

    data = target.read_bytes()
    assert b"\r\n" not in data, "baseline was written with CRLF line endings"
    assert b"1969\taaaaaaaaaaaa\tapp/server/session_phases.py\n" in data
    assert b"app/server/small.py" not in data, "files under the limit are not baselined"
