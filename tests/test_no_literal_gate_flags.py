"""Source guards: a gate flag that is a literal cannot ever go red.

RA-7433. Two specific regressions are cheap to reintroduce and expensive to
notice, because both look correct in review:

  1. `"tests_passed":   True` in the ship-gate row.
  2. `getattr(session, "sandbox_ok", True)` — a fail-open default in the
     episode recorder's trust anchor.

These assert on the source text, so they fire on the reintroduction itself
rather than waiting for a behavioural symptom that nothing observes.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASES = ROOT / "app" / "server" / "session_phases.py"
RECORDER = ROOT / "app" / "server" / "session_recorder.py"


def test_the_guard_can_see_the_files_it_guards():
    """Positive control. A guard that reads an empty string passes vacuously."""
    assert PHASES.is_file() and RECORDER.is_file()
    assert "tests_passed" in PHASES.read_text(encoding="utf-8")
    assert "sandbox_ok" in RECORDER.read_text(encoding="utf-8")


def test_ship_gate_tests_passed_is_not_a_literal():
    src = PHASES.read_text(encoding="utf-8")
    hits = re.findall(r'"tests_passed":\s*(True|False)\s*,', src)
    assert not hits, (
        f"ship gate writes a literal {hits} for tests_passed; it must come from "
        "session evidence so the field is able to go red"
    )


def test_recorder_trust_anchor_does_not_default_open():
    src = RECORDER.read_text(encoding="utf-8")
    hits = re.findall(r'getattr\(\s*session\s*,\s*"sandbox_ok"\s*,\s*True\s*\)', src)
    assert not hits, (
        "sandbox_ok is read with a fail-open True default; absent test evidence "
        "must not read as a pass"
    )
