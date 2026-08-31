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
        # Identity fields are clean here on purpose: a secret in `machine` or
        # `session_id` is now REFUSED rather than redacted (redacting an identity
        # destroys it and collides the primary key) — see the two tests below.
        "machine": "macbook",
        "digests": [{
            "session_id": "s1",
            "project_dir": f"/Users/phill/work {FAKE_OAUTH_TOKEN}",
            "title": f"t {FAKE_OAUTH_TOKEN}",
            "digest_md": f"body {FAKE_OAUTH_TOKEN}",
            "started_at": f"2026-08-30T01:00:00Z {FAKE_OAUTH_TOKEN}",
            "last_activity_at": f"2026-08-30T02:00:00Z {FAKE_OAUTH_TOKEN}",
        }],
    }
    r = client.post("/api/conversations/ingest", json=body, headers=HDR)
    assert r.status_code == 200, r.text
    row = store.saved[0]
    # EVERY caller-supplied string, enumerated from the row itself rather than
    # hand-listed, so a column added later is covered without anyone
    # remembering to extend this list.
    for field, value in row.items():
        assert FAKE_OAUTH_TOKEN not in str(value), f"{field} reached the store unredacted"
    assert {"id", "machine", "project_dir", "title", "digest_md",
            "started_at", "last_activity_at"} <= set(row), "the row lost a field this pins"
    # The response echoes the machine back, so it must be clean too.
    assert FAKE_OAUTH_TOKEN not in r.text


def test_a_secret_bearing_machine_name_is_refused_not_stored(convo, caplog):
    """Identity must be CLEAN, not merely redacted.

    Redacting an identity does not sanitise it, it destroys it: the row id is
    "<machine>:<session_id>", so two different secret-bearing values both become
    the same placeholder and therefore the same primary key — one machine's
    history silently overwriting another's. Storing "[REDACTED:...]" as a machine
    name would also be useless data in a table whose whole purpose is knowing
    which machine said what.

    `machine` applies to every digest in the request, so there is no partial
    recovery: the request is refused. The raw value must appear in neither the
    response nor the log — the 422 is what stops it reaching either.
    """
    client, _, store = convo
    body = {"machine": f"macbook {FAKE_OAUTH_TOKEN}", "digests": [{"session_id": "s1"}]}
    with caplog.at_level("INFO", logger="pi-ceo.routes.conversations"):
        r = client.post("/api/conversations/ingest", json=body, headers=HDR)
    assert r.status_code == 422
    assert FAKE_OAUTH_TOKEN not in r.text
    assert FAKE_OAUTH_TOKEN not in " ".join(rec.getMessage() for rec in caplog.records)
    assert store.saved == [], "nothing may be stored under an unusable identity"


def test_a_clean_machine_name_still_reaches_the_log(convo, caplog):
    """Green control. Without it, a validator that refused EVERY machine would
    satisfy the test above while taking the whole lane down."""
    client, _, _ = convo
    with caplog.at_level("INFO", logger="pi-ceo.routes.conversations"):
        assert client.post(
            "/api/conversations/ingest", json=ingest_body(), headers=HDR).status_code == 200
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "conversation digests stored" in logged, "the log line under test did not fire"
    assert "machine=macbook" in logged


def test_an_unidentifiable_digest_is_skipped_not_collided(convo):
    """One bad digest must not cost the batch, nor collide with another.

    Two different secret-bearing session ids redact to the SAME placeholder, so
    without this they would share a primary key and one would overwrite the
    other. Skipping them keeps every identifiable digest in the same request.
    """
    client, _, store = convo
    body = {
        "machine": "macbook",
        "digests": [
            {"session_id": f"a-{FAKE_OAUTH_TOKEN}", "digest_md": "first"},
            {"session_id": f"b-{FAKE_OAUTH_TOKEN}", "digest_md": "second"},
            {"session_id": "good-1", "digest_md": "keep me"},
        ],
    }
    r = client.post("/api/conversations/ingest", json=body, headers=HDR)
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == 2
    assert [row["id"] for row in store.saved] == ["macbook:good-1"]


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


def test_a_secret_bearing_timestamp_is_dropped_not_shipped_as_text(convo):
    """A bad timestamp must cost one field, not the whole batch.

    `started_at` and `last_activity_at` are TIMESTAMPTZ. A caller-supplied value
    carrying a secret is not a timestamp before redaction and is still not one
    after it — redaction turns it into text, which Postgres rejects just the
    same. The upsert is a SINGLE statement for the entire batch, so that one
    value would fail every digest sent alongside it, up to
    CONVERSATION_INGEST_MAX_ROWS of them.

    Both columns are nullable by design, so None keeps the row.
    """
    client, _, store = convo
    body = ingest_body()
    body["digests"][0]["started_at"] = f"2026-08-30T01:00:00Z {FAKE_OAUTH_TOKEN}"
    body["digests"][0]["last_activity_at"] = "not-a-timestamp-at-all"
    assert client.post(
        "/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    row = store.saved[0]
    assert row["started_at"] is None, "unparseable value must not be shipped as text"
    assert row["last_activity_at"] is None
    # The rest of the row still arrives — the point is that one bad field does
    # not cost the digest, let alone its batch.
    assert row["id"] == "macbook:sess-1"
    assert row["digest_md"]
    assert FAKE_OAUTH_TOKEN not in str(row)


def test_a_valid_timestamp_still_passes_through_untouched(convo):
    """Green control. Without this, dropping EVERY timestamp would satisfy the
    test above while silently destroying the ordering the search relies on
    (`order=last_activity_at.desc`)."""
    client, _, store = convo
    body = ingest_body()
    body["digests"][0]["started_at"] = "2026-08-30T01:00:00Z"
    body["digests"][0]["last_activity_at"] = "2026-08-30T02:00:00+10:00"
    assert client.post(
        "/api/conversations/ingest", json=body, headers=HDR).status_code == 200
    row = store.saved[0]
    assert row["started_at"] == "2026-08-30T01:00:00Z"
    assert row["last_activity_at"] == "2026-08-30T02:00:00+10:00"
