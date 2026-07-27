"""
test_job_success_record.py — RA-7085 job-authored last-success record.

Unit-locks the module that replaces mtime-of-newest-file health checks with a
job-authored, freshness-stamped success claim. Covers the Missed / Failed /
Late / Skipped taxonomy and the fail-closed reader (corrupt / malformed /
future-status records are never trusted as healthy).
"""
from __future__ import annotations

import json
import time

import pytest

import app.server.job_success_record as jsr


@pytest.fixture(autouse=True)
def isolated_dir(tmp_path, monkeypatch):
    d = tmp_path / "job-success"
    monkeypatch.setattr(jsr, "_job_success_dir", lambda: d)
    yield d


# ── write / read roundtrip ───────────────────────────────────────────────────

def test_record_success_roundtrip():
    assert jsr.record_success("job-a", detail="ok") is True
    rec = jsr.read_record("job-a")
    assert rec is not None
    assert rec["job_id"] == "job-a"
    assert rec["status"] == jsr.STATUS_OK
    assert rec["detail"] == "ok"
    assert isinstance(rec["ts"], (int, float))


def test_record_is_atomic_no_tmp_left_behind(isolated_dir):
    jsr.record_success("job-a")
    files = sorted(p.name for p in isolated_dir.iterdir())
    assert files == ["job-a.json"]  # no .json.tmp orphan


def test_missing_record_reads_none():
    assert jsr.read_record("never-ran") is None


def test_invalid_status_rejected_on_write():
    with pytest.raises(ValueError):
        jsr.record("job-a", "bogus")


# ── health verdict taxonomy ──────────────────────────────────────────────────

def test_fresh_ok_is_healthy():
    jsr.record_success("job-a", ts=time.time() - 3600)  # 1h old
    v = jsr.job_health("job-a", threshold_h=30.0)
    assert v.state == jsr.HEALTHY
    assert v.healthy is True
    assert v.age_h < 2


def test_stale_ok_is_stale_not_healthy():
    jsr.record_success("job-a", ts=time.time() - 48 * 3600)  # 48h old
    v = jsr.job_health("job-a", threshold_h=30.0)
    assert v.state == jsr.STALE
    assert v.healthy is False


def test_missing_is_missing():
    v = jsr.job_health("never-ran", threshold_h=30.0)
    assert v.state == jsr.MISSING
    assert v.age_h is None
    assert v.healthy is False


def test_failed_record_never_healthy_even_when_fresh():
    jsr.record_failed("job-a", ts=time.time() - 60)  # 1 min old
    v = jsr.job_health("job-a", threshold_h=30.0)
    assert v.state == jsr.FAILED
    assert v.healthy is False


def test_skipped_record_never_healthy_even_when_fresh():
    jsr.record_skipped("job-a", ts=time.time() - 60)
    v = jsr.job_health("job-a", threshold_h=30.0)
    assert v.state == jsr.SKIPPED
    assert v.healthy is False


# ── success_age_h: only genuine ok counts as proof of life ───────────────────

def test_success_age_h_fresh_ok():
    jsr.record_success("job-a", ts=time.time() - 2 * 3600)
    age = jsr.success_age_h("job-a")
    assert age is not None and 1.5 < age < 2.5


@pytest.mark.parametrize("status", [jsr.STATUS_FAILED, jsr.STATUS_SKIPPED])
def test_success_age_h_none_for_non_ok(status):
    jsr.record("job-a", status, ts=time.time() - 60)
    assert jsr.success_age_h("job-a") is None


def test_success_age_h_none_when_missing():
    assert jsr.success_age_h("never-ran") is None


# ── fail-closed reader: corrupt / malformed records are not trusted ──────────

def test_corrupt_json_reads_none(isolated_dir):
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text("{not json", encoding="utf-8")
    assert jsr.read_record("job-a") is None
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING


def test_unknown_status_reads_none(isolated_dir):
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        json.dumps({"job_id": "job-a", "status": "green", "ts": time.time()}),
        encoding="utf-8",
    )
    assert jsr.read_record("job-a") is None


@pytest.mark.parametrize("bad_ts", ["soon", None, True, float("inf"), float("nan")])
def test_malformed_ts_reads_none(isolated_dir, bad_ts):
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        json.dumps({"job_id": "job-a", "status": "ok", "ts": bad_ts}),
        encoding="utf-8",
    )
    # json can't serialize inf/nan by default → those are written as literals;
    # guard both the serialisable-bad and non-serialisable cases.
    rec = jsr.read_record("job-a")
    assert rec is None
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING


# ── Codex P1: a far-future ts must not clamp to age 0 and mask silence ────────

def test_far_future_ts_reads_none_and_is_missing():
    # A bogus ok record one year in the future must NOT read as healthy.
    jsr.record_success("job-a", ts=time.time() + 365 * 24 * 3600)
    assert jsr.read_record("job-a") is None
    assert jsr.success_age_h("job-a") is None
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING


def test_small_future_skew_tolerated():
    # Minor clock drift (< skew) is accepted and reads healthy (age ~0).
    jsr.record_success("job-a", ts=time.time() + 60)
    v = jsr.job_health("job-a", threshold_h=30.0)
    assert v.state == jsr.HEALTHY


# ── Codex P2: the record must claim exactly the requested job_id ─────────────

def test_missing_job_id_reads_none(isolated_dir):
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        json.dumps({"status": "ok", "ts": time.time()}),  # no job_id
        encoding="utf-8",
    )
    assert jsr.read_record("job-a") is None


def test_huge_int_ts_reads_none_not_raises(isolated_dir):
    # A JSON integer too large for float() (10**400) must fail closed, not
    # raise OverflowError up through the watchdog (Codex re-review P1).
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        '{"job_id": "job-a", "status": "ok", "ts": ' + "1" + "0" * 400 + "}",
        encoding="utf-8",
    )
    assert jsr.read_record("job-a") is None  # no exception
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING


def test_record_with_unconvertible_ts_returns_false_not_raises():
    # record()'s best-effort contract: a bad ts returns False, never raises.
    assert jsr.record("job-a", jsr.STATUS_OK, ts="not-a-number") is False
    assert jsr.read_record("job-a") is None


@pytest.mark.parametrize("bad_status", ["[]", "{}"])
def test_unhashable_status_reads_none_not_raises(isolated_dir, bad_status):
    # A JSON array/object `status` is unhashable; the set-membership test must
    # not raise TypeError out of read_record (Codex round-3 P1).
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        '{"job_id": "job-a", "status": ' + bad_status + ', "ts": 0}',
        encoding="utf-8",
    )
    assert jsr.read_record("job-a") is None  # no exception
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING


@pytest.mark.parametrize("bad_status", [[], {}, 3, None])
def test_record_unhashable_status_raises_valueerror_not_typeerror(bad_status):
    # An invalid non-string status is a programming error -> ValueError,
    # never a TypeError from set membership.
    with pytest.raises(ValueError):
        jsr.record("job-a", bad_status)


def test_mismatched_job_id_reads_none(isolated_dir):
    # A record whose job_id names a DIFFERENT job (e.g. file copied under this
    # job's name) must not count as proof for the requested job.
    isolated_dir.mkdir(parents=True, exist_ok=True)
    (isolated_dir / "job-a.json").write_text(
        json.dumps({"job_id": "some-other-job", "status": "ok", "ts": time.time()}),
        encoding="utf-8",
    )
    assert jsr.read_record("job-a") is None
    assert jsr.job_health("job-a", threshold_h=30.0).state == jsr.MISSING
