"""The handoff gate's pytest time limit must come from a measured clean run.

180 s, 420 s and RA-8171's load scaling over 420 s were each a guessed constant
the suite outgrew. On 06/11/2026 a clean-equivalent run of 9,394 tests took
679.54 s on the MacBook, so the 420 s base killed it at any load (rc=142).

The gate now records each CLEAN run's wall seconds in
``~/.receipts/pi-dev-ops/pytest-last-clean-seconds`` and uses
``max(420, ceil(1.5 x recorded))`` as the base, capped at 1500 s. These tests
drive the real gate block in ``scripts/handoff-loop.sh`` through bash with a
temporary HOME, so the real record is never touched, and a fake pytest that
passes, fails, or dies of SIGALRM the way the perl alarm kills a hung run.
"""
from __future__ import annotations

import importlib.util
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "pytest_time_limit.py"
GATE_SCRIPT = REPO_ROOT / "scripts" / "handoff-loop.sh"
RECORD = Path(".receipts") / "pi-dev-ops" / "pytest-last-clean-seconds"

FAKE_PY = """#!/bin/bash
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
  sleep 1.2
  case "$FAKE_PYTEST" in
    pass) exit 0 ;;
    fail) exit 1 ;;
    hang) kill -ALRM $$; sleep 5 ;;
  esac
  exit 3
fi
exec {real} "$@"
"""


def _gate_block() -> str:
    text = GATE_SCRIPT.read_text()
    match = re.search(r"# >>> pytest-limit\n(.*?)# <<< pytest-limit", text, re.S)
    assert match, "handoff-loop.sh has no measured pytest-limit block"
    return match.group(1)


def _run_block(tmp_path: Path, record: str | None, fake_pytest: str) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    if record is not None:
        (home / RECORD).parent.mkdir(parents=True)
        (home / RECORD).write_text(record)
    shim = tmp_path / "fake-python"
    shim.write_text(FAKE_PY.format(real=sys.executable))
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    script = "\n".join([
        "set -uo pipefail",
        f"LOG={tmp_path / 'gate.log'}",
        "PASS=0; FAIL=0; SKIP=0; PY_OK=1",
        f"PY={shim}",
        "log() { :; }; skip() { SKIP=$((SKIP+1)); }",
        'gate() { shift; if "$@" >/dev/null 2>&1; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi; }',
        _gate_block(),
        'echo "LIMIT=$PYTEST_LIMIT"',
        'echo "WHY=$PYTEST_LIMIT_WHY"',
        'echo "PASS=$PASS"',
        'echo "FAIL=$FAIL"',
    ])
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "FAKE_PYTEST": fake_pytest}
    out = subprocess.run(["bash", "-c", script], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=60).stdout
    result = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    rec = home / RECORD
    result["record"] = rec.read_text().strip() if rec.exists() else "<absent>"
    return result


def _base(result: dict[str, str]) -> int:
    match = re.search(r"\bbase=(\d+)s", result["WHY"])
    assert match, f"no base in limit reason: {result['WHY']!r}"
    return int(match.group(1))


def test_recorded_680_gives_base_1020(tmp_path: Path) -> None:
    result = _run_block(tmp_path, "680\n", "pass")
    assert _base(result) == 1020
    assert 1020 <= int(result["LIMIT"]) <= 1500


@pytest.mark.parametrize("record", [None, "garbage", "680.5", "-3", "0", "", "6²"])
def test_missing_or_bad_record_falls_back_to_420(tmp_path: Path, record: str | None) -> None:
    result = _run_block(tmp_path, record, "fail")
    assert _base(result) == 420
    assert 420 <= int(result["LIMIT"]) <= 1500


def test_recorded_2000_is_capped_at_1500(tmp_path: Path) -> None:
    result = _run_block(tmp_path, "2000", "fail")
    assert _base(result) == 1500
    assert int(result["LIMIT"]) == 1500


def test_clean_run_records_its_wall_seconds(tmp_path: Path) -> None:
    result = _run_block(tmp_path, None, "pass")
    assert result["PASS"] == "1"
    assert result["record"].isdigit() and int(result["record"]) >= 1


@pytest.mark.parametrize("outcome", ["fail", "hang"])
def test_failed_or_timed_out_run_never_writes_the_record(tmp_path: Path, outcome: str) -> None:
    result = _run_block(tmp_path, "680", outcome)
    assert result["FAIL"] == "1"
    assert result["record"] == "680"


def test_record_write_is_atomic_and_rejects_non_integers(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("pytest_time_limit", HELPER)
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    target = tmp_path / "deep" / "pytest-last-clean-seconds"
    helper.write_record(target, 700)
    assert target.read_text() == "700\n"
    assert [p.name for p in target.parent.iterdir()] == [target.name]
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    bad = subprocess.run([sys.executable, str(HELPER), "record", "12.5"], env=env,
                         capture_output=True, text=True, timeout=30)
    assert bad.returncode != 0 and not (tmp_path / RECORD).exists()
