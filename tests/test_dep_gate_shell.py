"""tests/test_dep_gate_shell.py — makes the dep_gate proof suite actually run.

`tests/estate/test_dep_gate.sh` is the red-then-green proof for
`scripts/estate/dep_gate.sh` (RA-7408). Without this wrapper it would not run
anywhere: `.github/workflows/ci.yml` runs `pytest tests/`, which does not collect
`.sh` files, and no workflow or `scripts/handoff-loop.sh` gate invokes shell
tests. Re-derive with:

    grep -rnE "tests/.*\\.sh|find tests" .github/workflows/ scripts/handoff-loop.sh

That gap is not hypothetical here. `tests/estate/test_bridge_failclosed.sh` has
sat in this repo unexecuted for exactly this reason, and RA-7408 is a ticket about
a guard that never fired because nothing ran it. Shipping the proof for that guard
into the same blind spot would have reproduced the defect one level up.

This wrapper follows `tests/test_claude_memory_backup_shell.py`, which solved the
same problem and documents the same reasoning. It is deliberately narrow for the
same reason that one is: a CI step for `tests/**/*.sh` wholesale would also pull in
`test_bridge_failclosed.sh`, which shells out to the `claude` CLI and would fail on
a runner for reasons unrelated to any change. Wiring that one in is a separate call.

This suite needs only bash and python3 — no `claude`, no network, no repo venv —
so it runs on a CI runner unmodified.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE = REPO_ROOT / "tests" / "estate" / "test_dep_gate.sh"
GATE = REPO_ROOT / "scripts" / "estate" / "dep_gate.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_the_dep_gate_shell_suite_passes() -> None:
    """Run the shell suite and surface its own report on failure.

    Asserting on the summary line as well as the exit code is deliberate: a suite
    that aborted before running anything also exits 0 in some shells, and
    "0 assertions passed" must not read the same as "every case held".
    """
    assert SUITE.exists(), f"{SUITE} is missing — the shell suite was moved or deleted"
    assert GATE.exists(), f"{GATE} is missing — RA-7408 regressed to its original state"
    proc = subprocess.run(
        ["bash", str(SUITE)],
        capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"dep_gate shell suite failed (rc={proc.returncode}):\n{out}"
    assert "fail=0" in out, f"dep_gate shell suite reported failures:\n{out}"
    # Guards against a suite that exits clean having asserted nothing.
    assert "pass=0" not in out, f"dep_gate shell suite ran no assertions:\n{out}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_the_live_gate_refuses_today() -> None:
    """The gate must BLOCK against the real manifest, and say why.

    This is the assertion that would notice if the gate were ever quietly loosened
    into passing while RA-7381's three founder inputs are still outstanding. It is
    checked here as well as inside the shell suite because this is the file CI runs:
    a regression that removed the shell suite entirely would still fail here.

    It is expected to CHANGE when the inputs arrive — at which point the gate should
    still refuse, but at the not-implemented history stage rather than on a missing
    binding. Either refusal keeps this green; only a pass would not.
    """
    proc = subprocess.run(
        ["bash", str(GATE)],
        capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        "dep_gate returned a PASSING verdict against the live manifest. "
        f"RA-7381's inputs are unresolved, so this must refuse:\n{out}"
    )
    assert "BLOCKED_DEPENDENCY" in out, f"expected a named refusal, got:\n{out}"
