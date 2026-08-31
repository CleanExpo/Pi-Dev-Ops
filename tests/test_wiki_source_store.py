"""tests/test_wiki_source_store.py — the Supabase layer under the wiki front door.

`tests/test_wiki_sources_api.py` fakes this module out entirely, so nothing there
exercises the queries it actually builds. A PostgREST param string is exactly the
kind of thing that breaks silently: a wrong filter returns rows rather than an
error, and a read that quietly drops `active=is.true` would feed the Librarian
retired requirements while looking perfectly healthy.

Two properties carry the weight:

  * a write reports what Supabase CONFIRMED, never what the caller sent
  * a read degrades to `[]` and never raises into the pipeline

Offline: `supabase_log._request` is replaced by a recorder, so nothing here can
reach a network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class Recorder:
    """Captures (method, path, body, prefer) and replays a canned response."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.calls: list[tuple[str, str, Any, str]] = []
        self._status = status
        self._body = body if body is not None else []

    def __call__(self, method: str, path: str, body: Any = None, prefer: str = "") -> tuple:
        self.calls.append((method, path, body, prefer))
        return self._status, self._body


@pytest.fixture
def store(monkeypatch):
    from app.server import supabase_log, wiki_source_store

    def install(status: int = 200, body: Any = None) -> Recorder:
        rec = Recorder(status, body)
        monkeypatch.setattr(supabase_log, "_request", rec)
        return rec

    return wiki_source_store, install


# ── writes report what Supabase confirmed ────────────────────────────────────


def test_a_write_reports_the_confirmed_row_not_the_sent_one(store):
    """`return=representation` is what makes the answer real. A 2xx alone proves
    only that the request was accepted, so a store reporting success off the
    status code would be reporting its own input back to itself."""
    ws, install = store
    rec = install(200, [{"id": "abc"}])
    assert ws.stage_source({"id": "abc"}) is True
    method, path, body, prefer = rec.calls[0]
    assert method == "POST" and path == "wiki_source_staging"
    assert body == [{"id": "abc"}], "the row must be sent as a single-element array"
    assert "return=representation" in prefer
    assert "resolution=merge-duplicates" in prefer, "a re-upload must upsert, not 409"


def test_a_write_that_confirms_nothing_is_false(store):
    """POSITIVE CONTROL. 2xx with an empty body is the silent-no-op shape, and it
    must not be reported as a successful stage."""
    ws, install = store
    install(200, [])
    assert ws.stage_source({"id": "abc"}) is False


def test_a_failed_write_is_false(store):
    ws, install = store
    install(500, None)
    assert ws.save_requirement({"id": "p:x"}) is False


# ── reads degrade, never raise ───────────────────────────────────────────────


def test_active_requirements_filters_on_project_and_active(store):
    """The filter is the whole point: without `active=is.true` a retired
    requirement keeps steering ingestion, and without the project filter one
    project's requirements leak into another's relevance scoring."""
    ws, install = store
    rec = install(200, [{"id": "pi-dev-ops:x"}])
    rows = ws.active_requirements("pi-dev-ops")
    assert rows == [{"id": "pi-dev-ops:x"}]
    path = rec.calls[0][1]
    assert "project_key=eq.pi-dev-ops" in path
    assert "active=is.true" in path


def test_reads_degrade_to_empty_on_failure(store):
    """A read must never raise into the pipeline — the Librarian falls back to
    its old index-only behaviour rather than the ingest cycle dying."""
    ws, install = store
    install(500, None)
    assert ws.active_requirements("pi-dev-ops") == []
    assert ws.queued_sources() == []
    assert ws.list_sources() == []


def test_an_empty_project_key_reads_nothing_rather_than_everything(store):
    """Without the guard this would drop the filter and return every project's
    requirements — which looks exactly like a working query."""
    ws, install = store
    rec = install(200, [{"id": "x"}])
    assert ws.active_requirements("") == []
    assert rec.calls == [], "no request may be issued at all"


def test_the_drain_read_asks_for_bodies_and_the_listing_does_not(store):
    """A listing of 50 staged rows would be megabytes if it carried body_md, and
    the drain is useless without it. The two reads must not converge."""
    ws, install = store
    rec = install(200, [])
    ws.queued_sources()
    ws.list_sources()
    drain_path, list_path = rec.calls[0][1], rec.calls[1][1]
    assert "body_md" in drain_path
    assert "body_md" not in list_path
    assert "status=eq.queued" in drain_path


# ── status hygiene ───────────────────────────────────────────────────────────


def test_mark_source_refuses_an_unknown_status_without_calling_supabase(store):
    """Enforced here rather than by a CHECK constraint (see the migration): the
    `sessions` table's status CHECK had to be dropped by RA-1407 when the
    lifecycle grew. Refusing in code keeps the guard without the migration trap.
    """
    ws, install = store
    rec = install(200, [{"id": "x"}])
    assert ws.mark_source("x", "definitely-not-a-status") is False
    assert rec.calls == [], "an invalid status must not reach the database"


@pytest.mark.parametrize("status", ["queued", "ingested", "quarantined", "error"])
def test_every_declared_status_is_accepted(store, status):
    """GREEN CONTROL. Without it, a validator that rejected everything would pass
    the test above while permanently stranding every staged row."""
    ws, install = store
    rec = install(200, [{"id": "x"}])
    assert ws.mark_source("x", status) is True
    assert rec.calls[0][0] == "PATCH"
    assert "id=eq.x" in rec.calls[0][1]


def test_body_id_is_content_addressed(store):
    ws, _ = store
    assert ws.body_id("same") == ws.body_id("same")
    assert ws.body_id("a") != ws.body_id("b")
    assert len(ws.body_id("x")) == 64


@pytest.mark.parametrize("raw,expected", [(100000, 100), (0, 1), (-5, 1), ("junk", 20)])
def test_limits_are_clamped(store, raw, expected):
    """`limit=100000` is not a page. A caller-supplied limit reaches PostgREST
    verbatim otherwise."""
    ws, _ = store
    assert ws._clamp(raw) == expected
