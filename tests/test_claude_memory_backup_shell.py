"""tests/test_claude_memory_backup_shell.py — makes the shell suite actually run.

`tests/test_claude_memory_backup.sh` guards the memory-backup script's path
resolution: that an explicitly-set CLAUDE_MEMORY_DIR is never silently replaced
by a different project's memory, and that an ambiguous match is refused rather
than guessed. Both are data-disclosure shapes — the script pushes whatever it
resolves to a git remote.

It would not have run anywhere. `.github/workflows/ci.yml` runs `pytest tests/`,
which does not collect `.sh` files, and no workflow or `scripts/handoff-loop.sh`
gate invokes shell tests — the repo's two other `.sh` suites
(`tests/estate/test_bridge_failclosed.sh`, `tests/test_delete_plaud_recording.sh`)
are manual-invocation-only today for the same reason. Re-derive with:

    grep -rnE "tests/.*\\.sh|find tests" .github/workflows/ scripts/handoff-loop.sh

This wrapper is deliberately narrow. Adding a CI step for `tests/**/*.sh`
wholesale would also pull in `test_bridge_failclosed.sh`, which shells out to the
`claude` CLI and so would fail on a runner for reasons that have nothing to do
with this change. Wiring those two in is a separate call.

The shell suite needs only bash, awk, grep and mktemp, and never reaches the
script's git/push path — it runs an awk-extracted slice of the resolution logic
and asserts that fact itself (case E0b, with E0c as its positive control).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE = REPO_ROOT / "tests" / "test_claude_memory_backup.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_the_memory_backup_shell_suite_passes() -> None:
    """Run the shell suite and surface its own report on failure.

    Asserting on the summary line as well as the exit code is deliberate: a
    suite that aborted before running anything also exits 0 in some shells, and
    "0 assertions passed" must not read the same as "every guard held".
    """
    assert SUITE.exists(), f"{SUITE} is missing — the shell suite was moved or deleted"
    proc = subprocess.run(
        ["bash", str(SUITE)],
        capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"shell suite failed (rc={proc.returncode}):\n{out}"
    assert "fail=0" in out, f"shell suite reported failures:\n{out}"
    # Guards against a suite that exits clean having asserted nothing.
    assert "pass=0" not in out, f"shell suite ran no assertions:\n{out}"
