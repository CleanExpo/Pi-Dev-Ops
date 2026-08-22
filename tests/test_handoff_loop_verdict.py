"""A skipped required gate must never read as READY.

The definition-of-done runner used to end with:

    if [ "$SKIP" -gt 0 ]; then
      log "VERDICT: READY (with $SKIP skipped ...)"
    ...
    exit 0

so only ``FAIL`` could set a non-zero exit. A checkout whose toolchain was not
provisioned skipped every real gate and still printed READY and exited 0 — the
runner reported "tested" when it meant "did not run". That shape was observed on
2026-08-22: ``pass=3 fail=0 skip=16`` verdict READY, on a branch whose suite was
actually red.

These tests drive the real ``scripts/handoff-loop.sh`` in an isolated root that
forces skips while making a genuine failure impossible, and pin the repaired
contract: skip is incomplete, incomplete is non-zero, and READY may not appear.
Run against the pre-repair script both assertions fail, which is what makes them
a control rather than a restatement.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "scripts" / "handoff-loop.sh"


def _run_gate_in_empty_root(tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the real gate runner with its ROOT pointed at an empty tree.

    ``handoff-loop.sh`` derives ROOT from its own location, so copying it into a
    bare directory is enough to isolate it. With no ``app/``, no ``dashboard/``
    and no ``scripts/secrets_check.py`` present, every stack-dependent gate takes
    its SKIP branch while ``clean-bloat`` still passes — SKIP > 0 and FAIL == 0,
    which is exactly the state that used to be reported as READY.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(GATE_SCRIPT, scripts_dir / "handoff-loop.sh")

    return subprocess.run(
        ["bash", str(scripts_dir / "handoff-loop.sh")],
        capture_output=True,
        text=True,
        timeout=180,
        # /tmp, never an external volume: this machine points TMPDIR at a removable
        # disk whose writes are denied, which fails gates for reasons unrelated to
        # the code under test.
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": "/tmp", "HOME": str(tmp_path)},
    )


@pytest.fixture(scope="module")
def gate_result(tmp_path_factory) -> subprocess.CompletedProcess:
    return _run_gate_in_empty_root(tmp_path_factory.mktemp("handoff_gate"))


def test_the_isolated_run_actually_skipped_gates(gate_result):
    """Premise check — without skips the other assertions would prove nothing."""
    assert "SKIP:" in gate_result.stdout, gate_result.stdout[-2000:]
    assert "   FAIL:" not in gate_result.stdout, (
        "a gate genuinely failed, so this run cannot test the skip path:\n"
        + gate_result.stdout[-2000:]
    )


def test_skipped_gates_do_not_produce_ready(gate_result):
    assert "VERDICT: READY" not in gate_result.stdout, (
        "a run with skipped gates reported READY:\n" + gate_result.stdout[-2000:]
    )
    assert "VERDICT: INCOMPLETE" in gate_result.stdout, gate_result.stdout[-2000:]


def test_skipped_gates_exit_non_zero(gate_result):
    assert gate_result.returncode != 0, (
        "a run with skipped gates exited 0, so callers read it as ready:\n"
        + gate_result.stdout[-2000:]
    )
