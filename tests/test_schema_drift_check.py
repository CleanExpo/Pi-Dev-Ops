"""Regression tests for scripts/schema_drift_check.py (RA-7399).

The ticket that asked for this named the trap in advance: *"A drift job that
silently fails to connect, or queries the wrong project, reports 'no drift' —
indistinguishable from a clean system."*

So the test that matters most here is
`test_empty_live_list_is_an_error_not_a_clean_bill_of_health`. Everything else
is arithmetic; that one is the reason the job is worth having.

Every test below was verified to FAIL against a deliberately broken
implementation, not merely to pass against the working one.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "schema_drift_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("schema_drift_check", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drift = _load()


def run(stdin: str) -> int:
    """Run the script as CI does, returning its exit code."""
    return subprocess.run(
        [sys.executable, str(_SCRIPT)], input=stdin, text=True,
        capture_output=True, cwd=REPO,
    ).returncode


# --------------------------------------------------------------------------
# the trap
# --------------------------------------------------------------------------

def test_empty_live_list_is_an_error_not_a_clean_bill_of_health():
    """THE point of this file.

    An empty live set is what a failed psql, a wrong credential, or the wrong
    project looks like from here. Treated as data it yields zero
    live-but-undeclared tables and prints "no drift" — a green produced by never
    reaching the database. Exit 2 distinguishes it from both 0 (clean) and
    1 (drift found).
    """
    assert run("") == 2
    assert run("   \n  \n") == 2


def test_a_real_live_list_does_not_trip_the_empty_guard():
    """The guard must not be so eager that nothing ever gets checked."""
    assert run("sessions\n") in (0, 1)   # a verdict, not the fail-closed code


# --------------------------------------------------------------------------
# both directions
# --------------------------------------------------------------------------

DECLARED = {"a": "m.sql", "b": "m.sql", "gone": "m.sql"}


def test_live_but_undeclared_is_reported():
    """The direction that blinds the RLS gate. No baseline, by design."""
    out = drift.classify(DECLARED, {"a", "b", "gone", "snuck_in"}, {})
    assert out["live_not_declared"] == ["snuck_in"]


def test_declared_but_absent_is_reported_unless_baselined():
    out = drift.classify(DECLARED, {"a", "b"}, {})
    assert out["declared_not_live"] == ["gone"]
    baselined = drift.classify(DECLARED, {"a", "b"}, {"gone": "never applied"})
    assert baselined["declared_not_live"] == []


def test_a_baselined_table_that_appears_live_must_leave_the_baseline():
    """Shrink-only, same ratchet as every other baseline in this repo."""
    out = drift.classify(DECLARED, {"a", "b", "gone"}, {"gone": "never applied"})
    assert out["baselined_now_live"] == ["gone"]
    assert out["declared_not_live"] == []


def test_a_clean_comparison_reports_nothing():
    out = drift.classify(DECLARED, {"a", "b", "gone"}, {})
    assert not any(out.values())


# --------------------------------------------------------------------------
# the declared side
# --------------------------------------------------------------------------

def test_declared_set_reads_all_three_sources():
    """migration.sql, migrations/*.sql AND mesh/schema/*.sql.

    The third is the one CLAUDE.md's own re-derivation command missed for
    months, under-reporting by the four mesh_* tables. A parser that reads two
    of three would call four live tables undeclared and cry drift every day.
    """
    declared = drift.declared_tables()
    assert "sessions" in declared, "base migration.sql not read"
    assert "mesh_work_claims" in declared, "mesh/schema not read"
    assert any("migrations/" in v for v in declared.values()), "migrations/ not read"


def test_source_files_are_found_at_all():
    assert len(drift.source_files()) > 10


def test_create_table_if_not_exists_is_matched():
    assert drift._CREATE.findall("create table if not exists public.foo (") == ["foo"]
    assert drift._CREATE.findall("CREATE TABLE bar(") == ["bar"]


def test_baseline_parses_name_and_reason():
    parsed = drift.read_baseline()
    assert parsed, "the committed baseline should not be empty"
    assert all(isinstance(k, str) and k.islower() for k in parsed)
