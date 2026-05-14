#!/usr/bin/env python3
"""scripts/backfill_dedupe_state.py — one-off seeder for the dedupe gate.

Context: the triage agent cancelled ~2,441 duplicate margot-idea tickets
in the Pi-Dev-Ops project. Without this backfill the three cron
generators (project_health_monitor, production_coordinator,
enhancement_scout) would simply re-file every one of them on the next
tick because their dedupe state files are empty.

What it does:
  1. Pages Linear for every `margot-idea` ticket in the Pi-Dev-Ops
     project created in the last 14 days (any state).
  2. Computes the canonical content hash (same algorithm as
     swarm._dedupe.content_hash).
  3. Routes each ticket to the correct generator state file via title
     prefix:
        [Production] …      → prod_coord
        [WorkOrder] …       → phm
        [Enhancement] …     → scout
        anything else       → scout (the catch-all)
  4. Appends one JSONL row per ticket using the ticket's actual
     createdAt timestamp — so the rolling-14d window respects when the
     ticket was originally filed, not when this script ran.

Idempotent-ish: re-running will append duplicate rows. That's fine for
the dedupe gate (still returns the same hash key) but if you re-run,
delete the three state files first to keep them tidy.

Usage:
    cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
    LINEAR_API_KEY=$(op read 'op://Private/Linear/api-key') \
        python3 scripts/backfill_dedupe_state.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / ".harness" / "swarm"
WINDOW_DAYS = 14

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
TARGET_LABEL = "margot-idea"
TARGET_PROJECT = "Pi - Dev -Ops"


# ── Content hash (replicated from swarm/_dedupe.py to keep this script
#    standalone — avoids pulling the whole swarm package's import chain). ──


def content_hash(title: str, body: str = "") -> str:
    norm_title = " ".join((title or "").lower().strip().split())
    norm_body = " ".join((body or "")[:500].lower().strip().split())
    raw = f"{norm_title}|{norm_body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── Linear paging ──


def _gql(query: str, variables: dict | None = None) -> dict:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        print("ERROR: LINEAR_API_KEY env var is empty", file=sys.stderr)
        sys.exit(2)
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_margot_idea_tickets() -> list[dict]:
    """Page every margot-idea ticket created in the last 14 days.

    Filters server-side on label name + createdAt cutoff. Project name
    filter is applied client-side after the fetch because Linear's filter
    grammar for project name is finicky and the page sizes here are small.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    out: list[dict] = []
    after: str | None = None
    while True:
        res = _gql(
            """
            query($after: String, $cutoff: DateTimeOrDuration!) {
              issues(
                first: 100,
                after: $after,
                filter: {
                  labels: { name: { eq: "margot-idea" } }
                  createdAt: { gte: $cutoff }
                }
              ) {
                nodes {
                  id identifier title description createdAt
                  project { name }
                  state { name }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
            """,
            {"after": after, "cutoff": cutoff},
        )
        data = (res.get("data") or {}).get("issues") or {}
        nodes = data.get("nodes") or []
        out.extend(nodes)
        if not data.get("pageInfo", {}).get("hasNextPage"):
            break
        after = data["pageInfo"]["endCursor"]
    return out


# ── Routing ──


def route_generator(title: str) -> str:
    """Map a ticket title to its source generator's state-file key.

    Heuristic per the dedupe brief (title prefix). The three cron
    generators format their titles consistently:
      * production_coordinator → `[Production] …`
      * project_health_monitor → `[WorkOrder] …`
      * enhancement_scout      → `[Enhancement] …`
    Anything else falls through to scout — that's the lane most likely to
    have produced bare-titled dupes via the Discovery loop.
    """
    t = (title or "").lstrip().lower()
    if t.startswith("[production]"):
        return "prod_coord"
    if t.startswith("[workorder]") or t.startswith("[work order]"):
        return "phm"
    if t.startswith("[enhancement]"):
        return "scout"
    return "scout"


# ── Append rows ──


def write_rows(rows_by_generator: dict[str, list[dict]]) -> dict[str, int]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for generator, rows in rows_by_generator.items():
        p = STATE_DIR / f"dedupe_{generator}.jsonl"
        with p.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        counts[generator] = len(rows)
    return counts


def main() -> int:
    print(f"Backfilling dedupe state from Linear (window: {WINDOW_DAYS}d)…")
    tickets = fetch_margot_idea_tickets()
    print(f"  fetched {len(tickets)} margot-idea tickets")

    # Filter to Pi-Dev-Ops project (client-side — keeps the GraphQL filter
    # tidy and lets us see what we discarded).
    pi_devops = [
        t for t in tickets
        if ((t.get("project") or {}).get("name") or "") == TARGET_PROJECT
    ]
    print(f"  {len(pi_devops)} in project '{TARGET_PROJECT}' "
          f"(dropped {len(tickets) - len(pi_devops)} from other projects)")

    rows_by_generator: dict[str, list[dict]] = {
        "scout": [], "phm": [], "prod_coord": [],
    }
    for t in pi_devops:
        title = t.get("title") or ""
        body = t.get("description") or ""
        identifier = t.get("identifier") or ""
        filed_at = t.get("createdAt") or datetime.now(timezone.utc).isoformat()
        generator = route_generator(title)
        rows_by_generator[generator].append({
            "hash": content_hash(title, body),
            "linear_id": identifier,
            "filed_at": filed_at,
        })

    counts = write_rows(rows_by_generator)
    print("Wrote dedupe state files:")
    for gen, n in counts.items():
        p = STATE_DIR / f"dedupe_{gen}.jsonl"
        print(f"  {p.relative_to(REPO_ROOT)}: +{n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
