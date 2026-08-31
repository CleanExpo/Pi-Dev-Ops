"""tests/test_conversations_api.py — the conversation route contract (Milestone 3).

The HTTP surface of the shared conversation brain:

* Every route refuses an unauthenticated caller (401) before doing any work.
* The whole lane is OFF unless CONVERSATION_SYNC_ENABLED=1 (503).
* Ingest reports a partial Supabase write as a failure instead of "ok".
* Rows are machine-scoped, capped, and batch-bounded.
* Search/recent pass arguments through and never fall back to an unfiltered list.

Two sibling files cover the rest of this lane, split out because the three
together exceed the repo's 300-line ceiling:
`test_conversations_redaction.py` (the server-side second redaction pass and its
fail-closed behaviour) and `test_conversation_store.py` (the Supabase layer
underneath these routes).

Fully offline: the Supabase layer is a recording fake, so nothing here can
reach a network.
"""
from __future__ import annotations

import pytest

from tests.conversation_helpers import HDR, FakeStore, ingest_body, make_convo


@pytest.fixture
def convo(monkeypatch):
    """(client, module, store) with auth configured and the lane enabled."""
    return make_convo(monkeypatch)


def test_every_route_401s_without_a_secret(convo):
    client, _, store = convo
    assert client.post("/api/conversations/ingest", json=ingest_body()).status_code == 401
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
        "/api/conversations/ingest", json=ingest_body(), headers=HDR).status_code == 503
    assert client.get("/api/conversations/search?q=x", headers=HDR).status_code == 503
    assert client.get("/api/conversations/recent", headers=HDR).status_code == 503
    assert store.saved == []


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
def test_the_server_accepts_the_same_truthy_values_as_the_collector(
    convo, monkeypatch, value):
    """The two halves of one switch must agree on what "on" means.

    The server took only the literal "1" while
    `scripts/conversation_collector.py` accepts {1,true,yes,on}. With
    CONVERSATION_SYNC_ENABLED=true every machine considered itself enabled and
    shipped into a 503 forever — and the fleet runbook told operators that value
    would work. Divergence here is silent on both sides, so it is pinned.
    """
    client, _, _ = convo
    monkeypatch.setenv("CONVERSATION_SYNC_ENABLED", value)
    assert client.get("/api/conversations/recent", headers=HDR).status_code == 200


@pytest.mark.parametrize("value", ["", " ", "0", "false", "off", "no"])
def test_nothing_outside_the_truthy_set_opens_the_lane(convo, monkeypatch, value):
    """Widening the accepted set must not weaken default-off."""
    client, _, _ = convo
    monkeypatch.setenv("CONVERSATION_SYNC_ENABLED", value)
    assert client.get("/api/conversations/recent", headers=HDR).status_code == 503


def test_disabled_lane_still_401s_anonymous_callers(convo, monkeypatch):
    """Auth is checked BEFORE the flag — an anonymous caller must not read this
    deployment's config state off the status code, and the declared smoke
    surfaces assert 401 whether or not the lane is on."""
    client, _, _ = convo
    monkeypatch.delenv("CONVERSATION_SYNC_ENABLED", raising=False)
    assert client.get("/api/conversations/recent").status_code == 401


def test_row_id_is_machine_scoped(convo):
    """The PK is "<machine>:<session_id>" so the same session id seen on two
    machines stays two rows instead of one overwriting the other."""
    client, _, store = convo
    assert client.post(
        "/api/conversations/ingest", json=ingest_body(), headers=HDR).status_code == 200
    row = store.saved[0]
    assert row["id"] == "macbook:sess-1"
    assert row["machine"] == "macbook"
    assert row["turn_count"] == 4


def test_digest_is_capped(convo, monkeypatch):
    client, conversations, store = convo
    monkeypatch.setattr(conversations, "CONVERSATION_DIGEST_MAX_CHARS", 50)
    body = ingest_body(digest="x" * 5000)
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
    r = client.post("/api/conversations/ingest", json=ingest_body(), headers=HDR)
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
