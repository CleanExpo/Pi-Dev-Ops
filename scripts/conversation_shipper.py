#!/usr/bin/env python3
"""conversation_shipper.py — posting digests, and believing the server's answer.

Extracted from `scripts/conversation_collector.py` at the 300-line ceiling, along
the seam that matters: collecting is local and repeatable, shipping is a network
call whose result decides whether a marker is written. A marker is never
revisited, so mis-reading a response loses a conversation permanently.

That is not hypothetical. This code used to treat any 2xx as "every row landed",
which was sound only while the ingest route rejected a partial write with 502 —
and stopped being sound the moment that route began skipping individual
unidentifiable digests and still returning 200. `_accounting` exists so the
client verifies what the server actually did instead of inferring it from a
status code.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Callable

log = logging.getLogger("pi-ceo.conversation_collector")

Poster = Callable[[str, dict, dict], tuple[int, str]]

BATCH_SIZE = 25  # server caps a request at CONVERSATION_INGEST_MAX_ROWS (200)
INGEST_PATH = "/api/conversations/ingest"
WIRE_FIELDS = ("project_dir", "title", "digest_md", "turn_count",
               "started_at", "last_activity_at")


def urllib_poster(url: str, headers: dict, payload: dict) -> tuple[int, str]:
    """Default poster. Replaced in tests so no test can reach the network."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, (response.read() or b"").decode(errors="replace")[:400]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:400].decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)[:400]


def _payload(batch: list[dict]) -> dict:
    """Ingest envelope {machine, digests[]}. The server re-derives each row id
    as "<machine>:<session_id>"; one run collects one machine's sessions."""
    return {"machine": batch[0]["machine"], "digests": [
        {"session_id": row["id"].split(":", 1)[1], **{f: row[f] for f in WIRE_FIELDS}}
        for row in batch]}


def _accounting(body: str, sent: int) -> tuple[int, int]:
    """(stored, skipped) as the server reported them, from its JSON response.

    The collector used to treat any 2xx as "all delivered". That was sound only
    while the route rejected a partial write with 502 — and it stopped being
    sound the moment the route began skipping individual unidentifiable digests
    and still returning 200. Trusting the status alone would mark those sessions
    shipped, and a marker is never revisited, so they would be lost silently.

    An older server, or an unparseable body, reports the optimistic default so
    this cannot start failing every batch against a deployment that predates the
    `stored`/`skipped` fields.
    """
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return sent, 0
    if not isinstance(payload, dict):
        return sent, 0
    stored = payload.get("stored")
    skipped = payload.get("skipped", 0)
    if not isinstance(stored, int) or not isinstance(skipped, int):
        return sent, 0
    return stored, skipped


def ship_rows(rows: list[dict], *, poster: Poster, url: str, secret: str) -> dict:
    """POST rows in batches. Returns counts and the first failure seen."""
    headers = {"Content-Type": "application/json", "X-Pi-CEO-Secret": secret}
    endpoint = f"{url.rstrip('/')}{INGEST_PATH}"
    sent = 0
    errors: list[str] = []
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        status, body = poster(endpoint, headers, _payload(batch))
        if not 200 <= status < 300:
            errors.append(f"HTTP {status}: {body[:120]}")
            log.error("conversation-collector: batch failed — HTTP %s", status)
            continue
        stored, skipped = _accounting(body, len(batch))
        if stored + skipped != len(batch):
            # Rows vanished for a reason the server did not name. Do NOT count
            # them: leaving the marker unwritten is what makes the next run
            # re-collect them.
            errors.append(
                f"HTTP {status}: server accounted for {stored + skipped} of {len(batch)}")
            log.error(
                "conversation-collector: batch under-accounted — stored=%d skipped=%d sent=%d",
                stored, skipped, len(batch))
            continue
        if skipped:
            # Deliberate, permanent refusals (an unidentifiable session id can
            # never become identifiable), so they are counted as delivered
            # rather than retried forever — but never silently.
            log.warning(
                "conversation-collector: server refused %d digest(s) in this batch as "
                "unidentifiable; they will not be retried", skipped)
        sent += len(batch)
    return {"sent": sent, "batches": (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE, "errors": errors}
