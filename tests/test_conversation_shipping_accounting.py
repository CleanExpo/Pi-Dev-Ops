"""tests/test_conversation_shipping_accounting.py — believing the server's answer.

A marker is never revisited: once the collector records a session as shipped,
that session is never re-collected. So mis-reading a response does not cause a
retry, it loses a conversation permanently.

`ship_rows` used to treat any 2xx as "every row landed". That was sound only
while the ingest route rejected a partial write with 502 — and it stopped being
sound the moment that route began skipping individual unidentifiable digests and
returning 200 with `skipped > 0`. These pin the repaired contract.

Fully offline: the poster is a stub.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import conversation_shipper as cs  # noqa: E402

# Shaped as collect_rows emits them: _payload strips the machine prefix off
# the id to recover session_id, so both fields have to be present.
ROWS = [{"id": f"mac:s{i}", "machine": "mac", "digest_md": "x",
         "project_dir": None, "title": "t", "turn_count": 1,
         "started_at": None, "last_activity_at": None} for i in range(3)]


def _poster(status: int, payload):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return lambda url, headers, data: (status, body)


def test_a_batch_the_server_under_accounted_is_not_counted_as_sent():
    """The row vanished for a reason the server did not name. Leaving it
    uncounted is what keeps the marker unwritten so the next run retries it."""
    res = cs.ship_rows(ROWS, poster=_poster(200, {"ok": True, "stored": 1, "skipped": 0}),
                       url="https://x", secret="s")
    assert res["sent"] == 0, "under-accounted rows must not be marked delivered"
    assert res["errors"] and "accounted for 1 of 3" in res["errors"][0]


def test_deliberately_skipped_digests_are_counted_but_reported(caplog):
    """A refusal the server NAMED is permanent — an unidentifiable session id
    can never become identifiable — so retrying forever would be a poison pill.
    Counted as delivered, but never silently: the warning is the record."""
    with caplog.at_level("WARNING", logger="pi-ceo.conversation_collector"):
        res = cs.ship_rows(ROWS, poster=_poster(200, {"ok": True, "stored": 2, "skipped": 1}),
                           url="https://x", secret="s")
    assert res["sent"] == 3
    assert res["errors"] == []
    assert "refused 1 digest" in " ".join(r.getMessage() for r in caplog.records)


def test_a_fully_stored_batch_is_clean():
    """Green control: the ordinary path must stay silent and fully counted, or
    an over-strict check would stall every sync."""
    res = cs.ship_rows(ROWS, poster=_poster(200, {"ok": True, "stored": 3, "skipped": 0}),
                       url="https://x", secret="s")
    assert res["sent"] == 3 and res["errors"] == []


def test_an_older_server_without_the_fields_still_ships():
    """Back-compat: a deployment predating stored/skipped must not fail every
    batch. The optimistic default restores the old behaviour for it alone."""
    for payload in ({"ok": True}, "not json at all"):
        res = cs.ship_rows(ROWS, poster=_poster(200, payload), url="https://x", secret="s")
        assert res["sent"] == 3, f"older-server shape {payload!r} broke shipping"
        assert res["errors"] == []


def test_a_non_2xx_is_still_an_error():
    res = cs.ship_rows(ROWS, poster=_poster(502, {"detail": "nope"}), url="https://x", secret="s")
    assert res["sent"] == 0 and res["errors"]
