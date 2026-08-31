"""tests/test_conversations_api.py — shared conversation brain (Milestone 3).

Proves the SERVER half of the cross-machine conversation store:

* Every route refuses an unauthenticated caller (401) before doing any work.
* The whole lane is OFF unless CONVERSATION_SYNC_ENABLED=1 (503).
* Ingest runs a SECOND redaction pass — a digest carrying a live-shaped
  Anthropic key must reach the store redacted. That is the milestone's whole
  premise, so it is asserted on the row that would actually be written rather
  than on the response body.
* Ingest reports a partial Supabase write as a failure instead of "ok".
* Search/recent pass arguments through and never fall back to an unfiltered list.

Fully offline: the Supabase layer is a recording fake, so nothing here can
reach a network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}

# Syntactically live-shaped, not real credentials: the prefix is real, the body
# is fixed filler. That is what makes them positive controls — the patterns MUST
# match, so a redactor that silently stopped running lets them through unchanged.
FAKE_ANTHROPIC_KEY = "sk-ant-api03-" + "A1b2C3d4E5" * 5
FAKE_OAUTH_TOKEN = "sk-ant-oat01-" + "Z9y8X7w6V5" * 4


class FakeStore:
    """Records what the route asked the Supabase layer to do."""

    def __init__(self, *, written: int | None = None) -> None:
        self.saved: list[dict[str, Any]] = []
        self.searches: list[tuple] = []
        self.recents: list[tuple] = []
        self._written = written

    def save(self, rows: list[dict[str, Any]]) -> int:
        self.saved.extend(rows)
        return len(rows) if self._written is None else self._written

    def search(self, query: str, *, machine=None, limit=20) -> list[dict[str, Any]]:
        self.searches.append((query, machine, limit))
        return [{"id": "mac:s1", "title": "hit"}]

    def recent(self, machine=None, limit=20) -> list[dict[str, Any]]:
        self.recents.append((machine, limit))
        return [{"id": "mac:s1", "title": "recent"}]


@pytest.fixture
def convo(monkeypatch):
    """(client, module, store) with auth configured and the lane enabled."""
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setenv("CONVERSATION_SYNC_ENABLED", "1")
    from app.server.routes import conversations
    monkeypatch.setattr(
        conversations.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    store = FakeStore()
    monkeypatch.setattr(
        conversations.conversation_store, "save_conversation_digests", store.save)
    monkeypatch.setattr(
        conversations.conversation_store, "search_conversation_digests", store.search)
    monkeypatch.setattr(
        conversations.conversation_store, "recent_conversation_digests", store.recent)
    app = FastAPI()
    app.include_router(conversations.router)
    return TestClient(app), conversations, store


def _ingest_body(digest: str = "hello", title: str = "t") -> dict[str, Any]:
    return {
        "machine": "macbook",
        "digests": [{
            "session_id": "sess-1",
            "project_dir": "/repo",
            "title": title,
            "digest_md": digest,
            "turn_count": 4,
            "started_at": "2026-08-30T01:00:00Z",
            "last_activity_at": "2026-08-30T02:00:00Z",
        }],
    }


def test_every_route_401s_without_a_secret(convo):
    client, _, store = convo
    assert client.post("/api/conversations/ingest", json=_ingest_body()).status_code == 401
    assert client.get("/api/conversations/search?q=deploy").status_code == 401
    assert client.get("/api/conversations/recent").status_code == 401
    assert store.saved == []  # refused before any write


def test_wrong_secret_is_401(convo):
    client, _, _ = convo
    r = client.get("/api/conversations/recent", headers={"X-Pi-CEO-Secret": "nope"})
    assert r.status_code == 401


@pytest.mark.parametrize("unset", [True, False])
def test_routes_refuse_when_sync_disabled(convo, monkeypatch, unset):
    """Unset OR "0" ⇒ every route 503s to an authed caller, nothing is stored."""
    client, _, store = convo
    if unset:
        monkeypatch.delenv("CONVERSATION_SYNC_ENABLED", raising=False)
    else:
        monkeypatch.setenv("CONVERSATION_SYNC_ENABLED", "0")
    assert client.post(
        "/api/conversations/ingest", json=_ingest_body(), headers=HDR).status_code == 503
    assert client.get("/api/conversations/search?q=x", headers=HDR).status_code == 503
    assert client.get("/api/conversations/recent", headers=HDR).status_code == 503
    assert store.saved == []


def test_disabled_lane_still_401s_anonymous_callers(convo, monkeypatch):
    """Auth is checked BEFORE the flag — an anonymous caller must not read this
    deployment's config state off the status code, and the declared smoke
    surfaces assert 401 whether or not the lane is on."""
    client, _, _ = convo
    monkeypatch.delenv("CONVERSATION_SYNC_ENABLED", raising=False)
    assert client.get("/api/conversations/recent").status_code == 401


def test_server_redacts_anthropic_key_before_storing(convo):
    """POSITIVE CONTROL. A digest whose client-side redaction "failed" arrives
    carrying a live-shaped Anthropic key; the row handed to Supabase must not
    contain it. Deleting the _redact() call in _row() makes this fail."""
    client, _, store = convo
    body = _ingest_body(digest=f"ran with ANTHROPIC_API_KEY={FAKE_ANTHROPIC_KEY} ok")
    r = client.post("/api/conversations/ingest", json=body, headers=HDR)
    assert r.status_code == 200, r.text
    assert len(store.saved) == 1
    stored = store.saved[0]["digest_md"]
    assert FAKE_ANTHROPIC_KEY not in stored
    assert "sk-ant-api03" not in stored
    assert "REDACTED" in stored


def test_server_redacts_secret_in_title(convo):
    """The title is indexed into the same tsvector as the body, so it needs the
    same pass — a secret in a title is as leaked as one in the digest."""
    client, _, store = convo
    body = _ingest_body(title=f"debugging {FAKE_ANTHROPIC_KEY}")
    assert client.post("/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    assert FAKE_ANTHROPIC_KEY not in (store.saved[0]["title"] or "")


def test_redaction_bank_covers_transcript_only_shapes(convo):
    """The sk-ant-oat OAuth token is absent from scanner._SECRET_PATTERNS and
    present only in the scripts/sync_claude_sessions bank, so this asserts the
    union is in force — if that import degrades, this is what says so."""
    client, _, store = convo
    body = _ingest_body(digest=f"token {FAKE_OAUTH_TOKEN}")
    assert client.post("/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    assert FAKE_OAUTH_TOKEN not in store.saved[0]["digest_md"]


def test_redaction_is_idempotent(convo):
    """A digest the client already redacted passes through unchanged, so a
    re-sync cannot accumulate nested placeholders."""
    from app.server.routes import conversations
    once = conversations._redact(f"k={FAKE_ANTHROPIC_KEY}")
    assert conversations._redact(once) == once


def test_row_id_is_machine_scoped(convo):
    """The PK is "<machine>:<session_id>" so the same session id seen on two
    machines stays two rows instead of one overwriting the other."""
    client, _, store = convo
    assert client.post(
        "/api/conversations/ingest", json=_ingest_body(), headers=HDR).status_code == 200
    row = store.saved[0]
    assert row["id"] == "macbook:sess-1"
    assert row["machine"] == "macbook"
    assert row["turn_count"] == 4


def test_digest_is_capped(convo, monkeypatch):
    client, conversations, store = convo
    monkeypatch.setattr(conversations, "CONVERSATION_DIGEST_MAX_CHARS", 50)
    body = _ingest_body(digest="x" * 5000)
    assert client.post(
        "/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    assert len(store.saved[0]["digest_md"]) == 50


def test_oversized_batch_rejected(convo, monkeypatch):
    client, conversations, store = convo
    monkeypatch.setattr(conversations, "CONVERSATION_INGEST_MAX_ROWS", 2)
    body = {"machine": "m", "digests": [
        {"session_id": f"s{i}"} for i in range(5)]}
    assert client.post(
        "/api/conversations/ingest", json=body, headers=HDR).status_code == 413
    assert store.saved == []


def test_partial_write_is_reported_as_failure(convo, monkeypatch):
    """A Supabase write that confirmed fewer rows than were sent must not be
    reported as ok — a machine told "stored" for a row that never landed keeps
    a hole in the shared lake with no signal it exists."""
    client, conversations, _ = convo
    partial = FakeStore(written=0)
    monkeypatch.setattr(
        conversations.conversation_store, "save_conversation_digests", partial.save)
    r = client.post("/api/conversations/ingest", json=_ingest_body(), headers=HDR)
    assert r.status_code == 502
    assert "0 of 1" in r.text


def test_missing_machine_rejected(convo):
    client, _, _ = convo
    body = {"machine": "   ", "digests": []}
    assert client.post(
        "/api/conversations/ingest", json=body, headers=HDR).status_code == 422


def test_search_passes_query_machine_and_limit(convo):
    client, _, store = convo
    r = client.get(
        "/api/conversations/search?q=deploy+failed&machine=nas&limit=5", headers=HDR)
    assert r.status_code == 200, r.text
    assert store.searches == [("deploy failed", "nas", 5)]
    assert r.json()["count"] == 1


def test_recent_passes_machine_and_limit(convo):
    client, _, store = convo
    r = client.get("/api/conversations/recent?machine=nas&limit=3", headers=HDR)
    assert r.status_code == 200
    assert store.recents == [("nas", 3)]
    assert r.json()["results"][0]["id"] == "mac:s1"
