"""tests/test_sources_drain.py — `sources_watcher.pull_staging()`.

The half of the knowledge front door that touches a filesystem.
`POST /api/wiki/sources/upload` puts a document into Supabase from anywhere;
this drains those rows into `Sources/` on the brain host, where `run_cycle()`
ingests them.

`tests/test_wiki_sources_api.py` proves the ROUTE refuses a hostile filename.
These prove the DRAIN refuses one too, which is a separate claim: the route
validated at insert time in another process, and a check performed elsewhere,
earlier, by different code is a claim rather than a guarantee. The table could
be written by a future caller, a migration, or by hand — and this is the code
that actually creates files.

The injection fixture `docs/briefs/estate-librarian-v1.md` §4 calls for is
`test_a_hostile_filename_writes_nothing_outside_sources`, which asserts on the
filesystem rather than on a return value.

Fully offline: the Supabase layer is a recording fake.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class FakeStore:
    """Stands in for app.server.wiki_source_store."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.marks: list[tuple[str, str, str | None]] = []

    def queued_sources(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._rows[:limit]

    def mark_source(self, source_id: str, status: str, reason: str | None = None) -> bool:
        self.marks.append((source_id, status, reason))
        return True


@pytest.fixture
def drain(monkeypatch, tmp_path):
    """(module, sources_dir, install) — install(rows) wires a fake store."""
    from swarm import sources_watcher

    sources = tmp_path / "Sources"
    sources.mkdir()
    monkeypatch.setattr(sources_watcher, "_sources_dir", lambda: sources)

    def install(rows: list[dict[str, Any]]) -> FakeStore:
        store = FakeStore(rows)
        import app.server.wiki_source_store as real
        monkeypatch.setattr(real, "queued_sources", store.queued_sources)
        monkeypatch.setattr(real, "mark_source", store.mark_source)
        return store

    return sources_watcher, sources, install


def _row(sid: str, filename: str, body: str = "content") -> dict[str, Any]:
    return {"id": sid, "filename": filename, "body_md": body, "status": "queued"}


def test_a_queued_row_becomes_a_file_and_is_marked_ingested(drain):
    """GREEN CONTROL. Without it, a drain that quarantined everything would
    satisfy every hostile-input test below while moving no document at all."""
    sw, sources, install = drain
    store = install([_row("a" * 64, "note.md", "hello world")])
    result = sw.pull_staging()
    assert result.written == ["note.md"]
    assert (sources / "note.md").read_text() == "hello world"
    assert store.marks == [("a" * 64, "ingested", None)]


@pytest.mark.parametrize("hostile", [
    "../escape.md",
    "../../.ssh/authorized_keys",
    "/etc/passwd",
    "sub/dir/page.md",
    "index.md",
    "log.md",
    "page.txt",
    "",
])
def test_a_hostile_filename_writes_nothing_outside_sources(drain, hostile, tmp_path):
    """THE INJECTION FIXTURE. Asserts on the FILESYSTEM, not a return value.

    A drain that returned "quarantined" while still having written the file
    would pass a return-value assertion and fail this one. Nothing may be
    created anywhere in the tree except inside Sources/, and Sources/ itself must
    stay empty because this row was never writable.
    """
    sw, sources, install = drain
    before = {p for p in tmp_path.rglob("*")}
    store = install([_row("b" * 64, hostile, "payload")])

    result = sw.pull_staging()

    assert result.written == []
    assert list(sources.iterdir()) == [], f"{hostile!r} produced a file"
    assert {p for p in tmp_path.rglob("*")} == before, f"{hostile!r} touched the tree"
    assert store.marks == [("b" * 64, "quarantined", "filename failed re-validation")]


def test_one_hostile_row_does_not_cost_the_good_rows_beside_it(drain):
    """A batch is not all-or-nothing. One bad row must not strand every other
    document in the same drain — the same rule the ingest batch paths follow."""
    sw, sources, install = drain
    store = install([
        _row("1" * 64, "../escape.md"),
        _row("2" * 64, "good-one.md", "kept"),
        _row("3" * 64, "good-two.md", "also kept"),
    ])
    result = sw.pull_staging()
    assert sorted(result.written) == ["good-one.md", "good-two.md"]
    assert result.quarantined == ["1" * 12]
    assert (sources / "good-one.md").read_text() == "kept"
    statuses = {sid[:1]: status for sid, status, _ in store.marks}
    assert statuses == {"1": "quarantined", "2": "ingested", "3": "ingested"}


def test_an_empty_queue_is_a_no_op(drain):
    """Runs on a schedule, so the common case is nothing to do. It must not
    create Sources/ churn or mark anything when the queue is empty."""
    sw, sources, install = drain
    store = install([])
    result = sw.pull_staging()
    assert result.written == [] and result.quarantined == [] and result.errors == []
    assert store.marks == []
    assert list(sources.iterdir()) == []


def test_a_write_failure_is_recorded_not_swallowed(drain, monkeypatch):
    """An unwritable destination must leave a trail. Marking `error` rather than
    `ingested` is what stops the row being reported as delivered."""
    sw, _sources, install = drain
    store = install([_row("c" * 64, "note.md")])

    def boom(*a: Any, **k: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    result = sw.pull_staging()
    assert result.written == []
    assert result.errors and "disk full" in result.errors[0]
    assert store.marks[0][1] == "error"
