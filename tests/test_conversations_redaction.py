"""tests/test_conversations_redaction.py — the server-side second redaction pass.

Split from `test_conversations_api.py`, which covers the route contract (auth,
kill switch, row shape, error reporting). These cover the property that makes
the lane safe to run at all: a digest reaching this server is redacted AGAIN
before anything is written, and when that second pass cannot be assembled the
write path closes rather than degrading.

Why a second pass exists: the client half runs on three machines that update
independently, so "the client already redacted it" is a claim the server cannot
verify, and the row it writes is durable.

The controls here are deliberately positive — each asserts on a live-SHAPED
token that the patterns must match. A redactor that silently stopped running
would return the input unchanged, which is indistinguishable from clean input
unless the fixture is one that has to be caught.

Fully offline: the Supabase layer is a recording fake.
"""
from __future__ import annotations

import sys

import pytest

from tests.conversation_helpers import (
    FAKE_ANTHROPIC_KEY,
    FAKE_OAUTH_TOKEN,
    HDR,
    ingest_body,
    make_convo,
)


@pytest.fixture
def convo(monkeypatch):
    return make_convo(monkeypatch)


def test_server_redacts_anthropic_key_before_storing(convo):
    """POSITIVE CONTROL. A digest whose client-side redaction "failed" arrives
    carrying a live-shaped Anthropic key; the row handed to Supabase must not
    contain it. Deleting the _redact() call in _row() makes this fail."""
    client, _, store = convo
    body = ingest_body(digest=f"ran with ANTHROPIC_API_KEY={FAKE_ANTHROPIC_KEY} ok")
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
    body = ingest_body(title=f"debugging {FAKE_ANTHROPIC_KEY}")
    assert client.post("/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    assert FAKE_ANTHROPIC_KEY not in (store.saved[0]["title"] or "")


def test_redaction_bank_covers_transcript_only_shapes(convo):
    """The Anthropic OAuth token shape is absent from scanner._SECRET_PATTERNS
    and present only in the scripts/sync_claude_sessions bank, so this asserts
    the union is in force — if that import degrades, this is what says so."""
    client, _, store = convo
    body = ingest_body(digest=f"token {FAKE_OAUTH_TOKEN}")
    assert client.post("/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    assert FAKE_OAUTH_TOKEN not in store.saved[0]["digest_md"]


def test_every_stored_field_is_redacted_not_just_the_obvious_two(convo):
    """POSITIVE CONTROL over the WHOLE row, not two columns of it.

    `project_dir` is a cwd, so it carries a username at minimum, and the client
    redacts it for exactly that reason — while this server, which exists because
    the client's claim cannot be verified, was copying it through verbatim along
    with `machine` and the `id` built from them. Asserting only on title and
    digest_md is what let three fields leak while the tests stayed green.
    """
    client, _, store = convo
    body = {
        "machine": f"macbook {FAKE_OAUTH_TOKEN}",
        "digests": [{
            "session_id": f"s1-{FAKE_OAUTH_TOKEN}",
            "project_dir": f"/Users/phill/work {FAKE_OAUTH_TOKEN}",
            "title": f"t {FAKE_OAUTH_TOKEN}",
            "digest_md": f"body {FAKE_OAUTH_TOKEN}",
        }],
    }
    r = client.post("/api/conversations/ingest", json=body, headers=HDR)
    assert r.status_code == 200, r.text
    row = store.saved[0]
    for field in ("id", "machine", "project_dir", "title", "digest_md"):
        assert FAKE_OAUTH_TOKEN not in str(row[field]), f"{field} reached the store unredacted"
    # The response echoes the machine back, so it must be clean too.
    assert FAKE_OAUTH_TOKEN not in r.text


def test_the_machine_name_is_redacted_before_it_is_logged(convo, caplog):
    """The log line took the raw body value, so a secret in `machine` landed in
    the server log even when every stored column was clean. Logs outlive
    requests and are shipped off-host, so that is a durable leak of its own."""
    client, _, _ = convo
    body = {"machine": f"macbook {FAKE_OAUTH_TOKEN}", "digests": [{"session_id": "s1"}]}
    with caplog.at_level("INFO", logger="pi-ceo.routes.conversations"):
        assert client.post(
            "/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "conversation digests stored" in logged, "the log line under test did not fire"
    assert FAKE_OAUTH_TOKEN not in logged


def test_redaction_is_idempotent(convo):
    """A digest the client already redacted passes through unchanged, so a
    re-sync cannot accumulate nested placeholders."""
    from app.server.routes import conversations
    once = conversations._redact(f"k={FAKE_ANTHROPIC_KEY}")
    assert conversations._redact(once) == once


def test_a_degraded_redaction_bank_closes_ingest(convo, monkeypatch):
    """FAIL CLOSED. If the transcript half of the bank did not load, the second
    pass cannot match the shapes transcripts actually carry, so accepting a
    digest would persist exactly what this route exists to strip. Ingest must
    503 and write nothing; the reads stay up, because rows already in the table
    were redacted by the bank in force when they were written."""
    client, conversations, store = convo
    monkeypatch.setattr(conversations, "_REDACTION_BANK_COMPLETE", False)
    r = client.post("/api/conversations/ingest", json=ingest_body(), headers=HDR)
    assert r.status_code == 503
    assert "redaction bank" in r.text
    assert store.saved == []
    assert client.get("/api/conversations/recent", headers=HDR).status_code == 200


def test_a_degraded_bank_is_still_401_for_anonymous_callers(convo, monkeypatch):
    """Auth stays first: the 503 must not tell an unauthenticated caller which
    banks this deployment managed to load."""
    client, conversations, _ = convo
    monkeypatch.setattr(conversations, "_REDACTION_BANK_COMPLETE", False)
    assert client.post(
        "/api/conversations/ingest", json=ingest_body()).status_code == 401


def test_a_failed_extension_import_reports_the_bank_incomplete(monkeypatch):
    """POSITIVE CONTROL for the flag itself.

    The test above monkeypatches `_REDACTION_BANK_COMPLETE`, which proves the
    route honours the flag but not that anything ever SETS it. This forces the
    real import to raise and asserts the builder reports incomplete — without
    it, `_build_redaction_bank` could return True unconditionally and both
    tests above would still pass.
    """
    import builtins

    from app.server.routes import conversations
    real_import = builtins.__import__

    def exploding_import(name, *a, **k):
        if name == "scripts.sync_claude_sessions":
            raise ImportError("simulated refactor over in scripts/")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "scripts.sync_claude_sessions", raising=False)
    monkeypatch.setattr(builtins, "__import__", exploding_import)
    bank, complete = conversations._build_redaction_bank()
    assert complete is False
    assert bank, "the scanner half should still compile — only the extension is missing"

    # And the healthy path reports complete, so `complete is False` above is a
    # real signal rather than a function that can only ever return False.
    monkeypatch.setattr(builtins, "__import__", real_import)
    _bank, healthy = conversations._build_redaction_bank()
    assert healthy is True
