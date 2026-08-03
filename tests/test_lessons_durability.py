"""tests/test_lessons_durability.py — RA-7111: cross-deploy lesson persistence.

The container filesystem is ephemeral (measured live 2026-08-03→04: a runtime append
raised the store to 50; the next deploy served exactly the 49-row seed again). Appends
write through to the lessons_durable Supabase table; boot hydrates table rows back into
the freshly seeded file. These tests fake ONLY the supabase_log boundary; per the store
doctrine they patch config.LESSONS_FILE and nothing else on the store side.
"""
import json
import os
import threading
import time

import pytest

from app.server import config, lessons, supabase_log


@pytest.fixture
def runtime_store(tmp_path, monkeypatch):
    path = tmp_path / "harness" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    assert not path.exists()
    return path


class _Captured(list):
    """Write-throughs arrive on a daemon thread (d83fa1e5 review: synchronous sends
    stalled the ship path). wait_for(n) makes assertions deterministic."""

    def wait_for(self, n: int, timeout: float = 5.0) -> "_Captured":
        deadline = time.monotonic() + timeout
        while len(self) < n and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(self) >= n, f"expected {n} write-through(s), saw {len(self)}"
        return self


@pytest.fixture
def captured(monkeypatch):
    """Capture write-throughs at the supabase_log boundary (thread-safe append)."""
    calls = _Captured()
    monkeypatch.setattr(supabase_log, "save_lesson", lambda e: (calls.append(e), True)[1])
    return calls


def test_append_writes_through(runtime_store, captured):
    entry = lessons.append_lesson("test", "unit-test", "durable please", "info")
    assert captured.wait_for(1) == [entry]
    assert any(e.get("lesson") == "durable please" for e in lessons.load_lessons(limit=1000))


def test_dedup_append_writes_through_new_entries_only(runtime_store, captured):
    assert lessons.append_lesson_dedup("a genuinely novel durable lesson", "workflow") is True
    captured.wait_for(1)
    assert captured[0]["text"] == "a genuinely novel durable lesson"
    # A near-duplicate takes the bump path: metadata rewrite, no new durable row.
    assert lessons.append_lesson_dedup("a genuinely novel durable lesson", "workflow") is False
    time.sleep(0.05)   # give a wrong extra write-through the chance to arrive
    assert len(captured) == 1, "the bump path must not write through a duplicate row"


def test_direct_writers_write_through(runtime_store, captured, monkeypatch):
    from app.server import pipeline
    from app.server.agents import feedback_loop as fl

    pipeline._append_ship_lesson("RA-777", 8.5)
    fl._write_outcome_lesson({"pipeline_id": "RA-778", "shipped_at": ""}, "positive")
    captured.wait_for(2)
    ids = [(e.get("pipeline_id"), e.get("cycle") or e.get("category")) for e in captured]
    assert ("RA-777", "ship") in ids
    assert ("RA-778", "outcome") in ids


def test_write_through_never_blocks_the_caller(runtime_store, monkeypatch):
    """P1 pin (d83fa1e5): a slow durable write must not stall the appending caller —
    the reviewer measured the ship path stalling by the full stub latency. Deterministic
    (event-gated, not timing-based): append_lesson must RETURN while save_lesson is
    still parked on an Event only this test releases."""
    release = threading.Event()
    finished = threading.Event()
    seen: dict = {}

    def parked_save(entry):
        seen["thread"] = threading.current_thread().name
        release.wait(5)
        finished.set()
        return True

    monkeypatch.setattr(supabase_log, "save_lesson", parked_save)
    entry = lessons.append_lesson("test", "unit-test", "must not block", "info")
    assert entry["lesson"] == "must not block"
    assert not finished.is_set(), "append_lesson blocked until the durable write finished"
    release.set()
    assert finished.wait(5), "the parked write-through never completed after release"
    assert seen.get("thread") != "MainThread", "write-through ran on the caller's thread"


def test_write_through_failure_never_breaks_append(runtime_store, monkeypatch, caplog):
    def boom(_e):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(supabase_log, "save_lesson", boom)
    with caplog.at_level("WARNING"):
        entry = lessons.append_lesson("test", "unit-test", "must land locally", "info")
    assert entry["lesson"] == "must land locally"
    assert any(e.get("lesson") == "must land locally" for e in lessons.load_lessons(limit=1000))
    assert any("write-through failed" in r.getMessage() for r in caplog.records)


def test_hydration_appends_and_advances_watermark(runtime_store, monkeypatch):
    fetched_with: list[str] = []
    rows = [
        {"line": {"ts": "t1", "source": "old-container", "category": "c",
                  "lesson": "survived the deploy", "severity": "info"},
         "created_at": "2026-08-04T01:00:00+00:00"},
        {"line": {"ts": "t2", "source": "old-container", "category": "c",
                  "lesson": "also survived", "severity": "info"},
         "created_at": "2026-08-04T02:00:00+00:00"},
    ]

    def fake_fetch(watermark):
        fetched_with.append(watermark)
        # gte semantics: the boundary row is re-served on the second call — the
        # content-hash reconciliation must skip it, not duplicate it.
        return rows if not fetched_with[1:] else [rows[-1]]

    monkeypatch.setattr(supabase_log, "fetch_lessons_since", fake_fetch)
    lessons.ensure_seeded()
    n = lessons.hydrate_from_durable()
    assert n == 2
    got = [e.get("lesson") for e in lessons.load_lessons(limit=1000)]
    assert "survived the deploy" in got and "also survived" in got
    wm = open(str(runtime_store) + ".hydrated-at", encoding="utf-8").read()
    assert wm == "2026-08-04T02:00:00+00:00"
    before = runtime_store.read_bytes()
    assert lessons.hydrate_from_durable() == 0, "re-served boundary row was duplicated"
    assert fetched_with[1] == "2026-08-04T02:00:00+00:00"
    assert runtime_store.read_bytes() == before


def test_hydration_dedups_rows_already_present_locally(runtime_store, captured, monkeypatch):
    """P1 probe (58e28fc4): on a RETAINED filesystem, a runtime append reaches both the
    file and the table without advancing the watermark; the next hydration re-fetches it
    and, at 58e28fc4, duplicated it. Content reconciliation must skip it."""
    entry = lessons.append_lesson("test", "unit-test", "already local", "info")
    monkeypatch.setattr(
        supabase_log, "fetch_lessons_since",
        lambda _w: [{"line": entry, "created_at": "2026-08-04T03:00:00+00:00"}],
    )
    before = [e.get("lesson") for e in lessons.load_lessons(limit=1000)].count("already local")
    assert before == 1
    assert lessons.hydrate_from_durable() == 0, "locally present row was re-appended"
    after = [e.get("lesson") for e in lessons.load_lessons(limit=1000)].count("already local")
    assert after == 1


def test_hydration_boundary_rows_neither_dropped_nor_duplicated(runtime_store, monkeypatch):
    """P1 probe (58e28fc4): with the strict gt-cursor, row B sharing the watermark
    timestamp of already-hydrated row A was permanently omitted. gte + hash dedup must
    pick up B without duplicating A."""
    T = "2026-08-04T05:00:00+00:00"
    row_a = {"line": {"ts": "a", "source": "s", "category": "c",
                      "lesson": "row A at the boundary", "severity": "info"}, "created_at": T}
    row_b = {"line": {"ts": "b", "source": "s", "category": "c",
                      "lesson": "row B late-visible at the boundary", "severity": "info"}, "created_at": T}
    batches = [[row_a], [row_a, row_b]]
    monkeypatch.setattr(supabase_log, "fetch_lessons_since", lambda _w: batches.pop(0))
    lessons.ensure_seeded()
    assert lessons.hydrate_from_durable() == 1
    assert lessons.hydrate_from_durable() == 1, "late-visible boundary row was dropped"
    got = [e.get("lesson") for e in lessons.load_lessons(limit=1000)]
    assert got.count("row A at the boundary") == 1
    assert got.count("row B late-visible at the boundary") == 1


def test_hydration_rejects_wrong_shaped_jsonb(runtime_store, monkeypatch, caplog):
    """P1 pin (d83fa1e5): a PRESENT but non-object `line` (scalar/list JSONB) was
    appended, persisted, and then crashed every reader with AttributeError. Ingestion
    must refuse non-dict rows; readers stay uncrashed."""
    T = "2026-08-04T08:00:00+00:00"
    rows = [
        {"line": 42, "created_at": T},                       # the reviewer's scalar probe
        {"line": ["a", "list"], "created_at": T},
        {"line": {"ts": "ok", "source": "s", "category": "c",
                  "lesson": "the only valid row", "severity": "info"}, "created_at": T},
    ]
    monkeypatch.setattr(supabase_log, "fetch_lessons_since", lambda _w: rows)
    lessons.ensure_seeded()
    with caplog.at_level("WARNING"):
        assert lessons.hydrate_from_durable() == 1
    assert sum("malformed durable lesson row" in r.getMessage() for r in caplog.records) == 2
    # The poison never reaches the file: every reader keeps working.
    got = lessons.load_lessons(limit=1000)
    assert any(e.get("lesson") == "the only valid row" for e in got)
    assert lessons.search_lessons_keyword("valid row") is not None   # no AttributeError


def test_hydration_skips_malformed_rows_and_retries_idempotently(runtime_store, monkeypatch, caplog):
    """P1 probe (58e28fc4): a malformed row 2 raised KeyError AFTER row 1 was appended,
    left no watermark, and duplicated row 1 on retry. Now: malformed rows skip with a
    warning, valid rows land, the watermark still advances, and a retry appends nothing."""
    T1, T3 = "2026-08-04T06:00:00+00:00", "2026-08-04T07:00:00+00:00"
    rows = [
        {"line": {"ts": "1", "source": "s", "category": "c", "lesson": "valid one", "severity": "info"},
         "created_at": T1},
        {"created_at": T1},  # no "line" key — the reviewer's KeyError probe
        {"line": {"ts": "3", "source": "s", "category": "c", "lesson": "valid three", "severity": "info"},
         "created_at": T3},
    ]
    monkeypatch.setattr(supabase_log, "fetch_lessons_since", lambda _w: rows)
    lessons.ensure_seeded()
    with caplog.at_level("WARNING"):
        assert lessons.hydrate_from_durable() == 2
    assert any("malformed durable lesson row" in r.getMessage() for r in caplog.records)
    wm = open(str(runtime_store) + ".hydrated-at", encoding="utf-8").read()
    assert wm == T3, "watermark must still advance past a malformed row"
    assert lessons.hydrate_from_durable() == 0, "retry after partial batch duplicated rows"
    got = [e.get("lesson") for e in lessons.load_lessons(limit=1000)]
    assert got.count("valid one") == 1 and got.count("valid three") == 1


def test_hydration_failure_is_nonfatal_and_logged(runtime_store, monkeypatch, caplog):
    def boom(_w):
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr(supabase_log, "fetch_lessons_since", boom)
    lessons.ensure_seeded()
    before = runtime_store.read_bytes()
    with caplog.at_level("WARNING"):
        assert lessons.hydrate_from_durable() == 0
    assert runtime_store.read_bytes() == before, "a failed hydration must not touch the store"
    assert any("hydration failed" in r.getMessage() for r in caplog.records)


def test_save_lesson_hash_is_stable_and_content_addressed(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(supabase_log, "_upsert", lambda t, r: (rows.append((t, r)), True)[1])
    entry = {"ts": "t", "lesson": "same content"}
    supabase_log.save_lesson(entry)
    supabase_log.save_lesson(dict(entry))          # equal content, distinct object
    supabase_log.save_lesson({"ts": "t", "lesson": "different"})
    assert rows[0][0] == "lessons_durable"
    assert rows[0][1]["hash"] == rows[1][1]["hash"], "equal content must hash equal (idempotent retries)"
    assert rows[0][1]["hash"] != rows[2][1]["hash"]
    assert rows[0][1]["line"] == entry
