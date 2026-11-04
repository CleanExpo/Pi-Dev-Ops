"""RA-8171: the handoff gate's pytest time limit must follow machine load.

``scripts/handoff-loop.sh`` bounded ``pytest tests/`` with a fixed 420 s alarm.
On a 10-core MacBook at load 11-14 (other agents running their own suites) a
clean run was killed at about 89% with zero failures, which blocked every
receipt. The limit was measuring the machine, not the code.

The limit is now ``420 x max(1, load1 / cpus)``, capped at 1500 s, computed by
``scripts/pytest_time_limit.py``. These tests fail on the pre-fix tree: the
helper does not exist there, and the shell script still hard-codes 420.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "pytest_time_limit.py"
GATE_SCRIPT = REPO_ROOT / "scripts" / "handoff-loop.sh"


def _helper():
    spec = importlib.util.spec_from_file_location("pytest_time_limit", HELPER)
    assert spec and spec.loader, f"missing helper: {HELPER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_high_load_raises_the_limit_above_base() -> None:
    # The observed failure: load 14 on 10 cores.
    assert _helper().time_limit(14.0, 10) > 420


def test_high_load_scales_linearly() -> None:
    assert _helper().time_limit(14.0, 10) == 588


def test_low_load_keeps_the_base_limit() -> None:
    helper = _helper()
    assert helper.time_limit(2.0, 10) == 420
    assert helper.time_limit(10.0, 10) == 420
    assert helper.time_limit(0.0, 10) == 420


def test_extreme_load_is_capped_so_a_hang_still_dies() -> None:
    assert _helper().time_limit(100.0, 10) == 1500


def test_bad_inputs_fall_back_to_base_not_unbounded() -> None:
    helper = _helper()
    assert helper.time_limit(float("nan"), 10) == 420
    assert helper.time_limit(float("inf"), 10) == 420
    assert helper.time_limit(-5.0, 10) == 420
    assert helper.time_limit(14.0, 0) == 1500  # 0 cores -> treated as 1


def test_cli_prints_a_bounded_integer_and_a_reason() -> None:
    out = subprocess.run(
        [sys.executable, str(HELPER)], capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    limit, _, reason = out.partition(" ")
    assert 420 <= int(limit) <= 1500
    assert "load1=" in reason and "cpus=" in reason


def test_no_environment_override_exists() -> None:
    # The release receipt re-runs the gate with no env; a caller must not be
    # able to switch the limit off or stretch it.
    assert "environ" not in HELPER.read_text()
    assert "getenv" not in HELPER.read_text()


def test_gate_feeds_the_computed_limit_to_the_alarm() -> None:
    text = GATE_SCRIPT.read_text()
    assert "scripts/pytest_time_limit.py" in text
    assert not re.search(r"exec @ARGV'\s+420\b", text), "fixed 420 s alarm still present"
    assert re.search(r"exec @ARGV'\s+\"\$PYTEST_LIMIT\"", text)
