"""RA-7317 — a cron store that parses but holds the wrong shape is a finding.

`json.loads` succeeds on a bare scalar, so such a store never reached the
JSONDecodeError branch. It reached the job loop instead, where a str iterates as
characters until `.get()` raises AttributeError and takes the whole sweep down —
a monitor that dies on malformed input reports nothing about anything.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SWEEP_SCRIPT = Path(
    os.environ.get("CRON_ERROR_SWEEP_SCRIPT", ROOT / "scripts" / "cron_error_sweep.py")
)
SPEC = importlib.util.spec_from_file_location("cron_error_sweep_under_test", SWEEP_SCRIPT)
assert SPEC and SPEC.loader
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def store_holding(tmp_path: Path, payload: str) -> list[tuple[str, Path]]:
    (tmp_path / "cron").mkdir(parents=True)
    (tmp_path / "cron" / "jobs.json").write_text(payload)
    return sweep.discover_stores(tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        "5",
        '"a job store, allegedly"',
        "null",
        "true",
        '{"updated_at": "2026-08-21T00:00:00+10:00"}',
        '{"jobs": ["not-a-job-object"]}',
    ],
)
def test_wrong_shape_reports_unreadable_instead_of_crashing(tmp_path, payload):
    found = sweep.failing_jobs(store_holding(tmp_path, payload))

    assert len(found) == 1
    assert found[0]["kind"] == "UNREADABLE"
    assert "UNREADABLE STORE" in found[0]["name"]


def test_a_bare_list_store_is_still_read(tmp_path):
    """The `raw if not a dict` fallback is deliberate — do not regress it."""
    payload = json.dumps([{"id": "bare01", "name": "listed flat", "last_status": "error"}])

    found = sweep.failing_jobs(store_holding(tmp_path, payload))

    assert [f["id"] for f in found] == ["bare01"]


def test_a_healthy_store_stays_silent(tmp_path):
    """Negative control: the guard must not turn a valid store into a finding."""
    payload = json.dumps({"jobs": [{"id": "ok01", "name": "fine", "last_status": "ok"}]})

    assert sweep.failing_jobs(store_holding(tmp_path, payload)) == []


@pytest.mark.parametrize("stamp", [5, 1.5, True, ["2026-01-01"], {"at": "x"}, None])
def test_a_non_string_timestamp_is_an_unknown_age_not_a_crash(stamp):
    """`fromisoformat` raises TypeError, not ValueError, on a non-str — so the except
    clause missed it and one malformed job took the whole sweep down."""
    assert sweep._age_days(stamp) is None


def test_a_job_with_a_numeric_timestamp_is_still_reported(tmp_path):
    """The finding must survive the bad field, not be lost with it."""
    payload = json.dumps({"jobs": [
        {"id": "bad01", "name": "numeric stamp", "last_status": "error",
         "last_run_at": 1755734400, "last_error": "synthetic"},
    ]})

    found = sweep.failing_jobs(store_holding(tmp_path, payload))

    assert [f["id"] for f in found] == ["bad01"]
    assert found[0]["age"] is None
    assert "never run" in sweep.render(found)


def test_a_non_utf8_store_is_a_finding_not_a_crash(tmp_path):
    """UnicodeDecodeError is a ValueError, not an OSError or a JSONDecodeError, so a
    store in the wrong encoding walked past a handler that named only its sibling."""
    (tmp_path / "cron").mkdir(parents=True)
    (tmp_path / "cron" / "jobs.json").write_bytes(b'\xff\xfe{"jobs": []}')

    found = sweep.failing_jobs(sweep.discover_stores(tmp_path))

    assert len(found) == 1
    assert found[0]["kind"] == "UNREADABLE"
    assert "UnicodeDecodeError" in found[0]["error"]
