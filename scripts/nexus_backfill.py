"""Historical backfill CLI for nexus outcomes.

Phase C / C3. Pulls historical events from Stripe / Vercel / Linear
APIs, runs them through the existing nexus.ingest parsers, and writes
the resulting Outcome rows to the SupabaseOutcomesStore.

Idempotent: outcome.id is derived from SHA-256(provider:event_id), so
re-running the backfill over the same window is a no-op (Postgres
upsert collision).

Default mode is --dry-run: prints what WOULD be written. Add --apply
to actually write.

Usage:
    python -m scripts.nexus_backfill --provider stripe \\
        --workspace acme --workspace-id ws-1 \\
        --since 2026-04-01 [--apply]

Environment variables (read at runtime, no CLI flags for secrets):
    NEXT_PUBLIC_SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    STRIPE_API_KEY
    LINEAR_API_KEY
    VERCEL_API_TOKEN
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

# Add project root for in-repo imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm.nexus.ingest import linear as ingest_linear  # noqa: E402
from swarm.nexus.ingest import stripe as ingest_stripe  # noqa: E402
from swarm.nexus.ingest import vercel as ingest_vercel  # noqa: E402
from swarm.nexus.outcomes import outcomes_store_factory  # noqa: E402

log = logging.getLogger("nexus_backfill")

DEFAULT_SINCE_DAYS = 30


# ============================================================
# Event fetcher Protocol — injectable for tests
# ============================================================


class EventFetcher(Protocol):
    """Fetch raw provider events since `since_iso`. Yields webhook-shaped
    dicts that match what the live webhook would have delivered."""

    def fetch(self, *, since_iso: str, workspace_slug: str,
              workspace_id: str) -> Iterable[dict[str, Any]]: ...


# ============================================================
# Live fetchers (network — only used in --apply mode)
# ============================================================


class StripeFetcher:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def fetch(self, *, since_iso: str, workspace_slug: str,
              workspace_id: str) -> Iterable[dict[str, Any]]:
        since_ts = int(datetime.fromisoformat(since_iso).timestamp())
        params = urllib.parse.urlencode({
            "created[gte]": since_ts,
            "limit": "100",
        })
        url = f"https://api.stripe.com/v1/invoices?{params}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for inv in data.get("data", []):
            if inv.get("status") != "paid":
                continue
            yield {
                "id": inv["id"],
                "type": "invoice.paid",
                "data": {"object": {
                    "id": inv["id"],
                    "amount_paid": inv.get("amount_paid"),
                    "metadata": {
                        "workspace_slug": workspace_slug,
                        "workspace_id": workspace_id,
                    },
                }},
            }


class VercelFetcher:
    def __init__(self, api_token: str, project_id: str) -> None:
        self._token = api_token
        self._project_id = project_id

    def fetch(self, *, since_iso: str, workspace_slug: str,
              workspace_id: str) -> Iterable[dict[str, Any]]:
        since_ms = int(datetime.fromisoformat(since_iso).timestamp() * 1000)
        params = urllib.parse.urlencode({
            "projectId": self._project_id,
            "since": str(since_ms),
            "limit": "100",
        })
        url = f"https://api.vercel.com/v6/deployments?{params}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._token}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for dep in data.get("deployments", []):
            if dep.get("state") != "READY":
                continue
            yield {
                "id": dep["uid"],
                "type": "deployment.succeeded",
                "payload": {
                    "workspace_slug": workspace_slug,
                    "workspace_id": workspace_id,
                    "deployment": {"url": dep.get("url")},
                },
            }


class LinearFetcher:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def fetch(self, *, since_iso: str, workspace_slug: str,
              workspace_id: str) -> Iterable[dict[str, Any]]:
        query = (
            'query Issues($since: DateTimeOrDuration!) {'
            '  issues(filter: {completedAt: {gte: $since}}, first: 100) {'
            '    nodes { id title completedAt state { type } }'
            '  }'
            '}'
        )
        payload = json.dumps({"query": query, "variables": {"since": since_iso}}).encode()
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=payload,
            headers={
                "Authorization": self._key,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for issue in (data.get("data", {}).get("issues", {}) or {}).get("nodes", []):
            yield {
                "deliveryId": f"backfill-linear-{issue['id']}",
                "type": "Issue",
                "action": "update",
                "workspace_slug": workspace_slug,
                "workspace_id": workspace_id,
                "data": {
                    "id": issue["id"],
                    "title": issue.get("title", ""),
                    "state": {"type": "completed"},
                },
            }


# ============================================================
# Core backfill loop — pure logic, testable
# ============================================================


_PARSERS = {
    "stripe": ingest_stripe.parse,
    "vercel": ingest_vercel.parse,
    "linear": ingest_linear.parse,
}


def backfill(
    *,
    provider: str,
    workspace_slug: str,
    workspace_id: str,
    since_iso: str,
    fetcher: EventFetcher,
    outcomes_store: Any,
    apply: bool,
) -> dict[str, int]:
    """Pull events → parse → (write or print). Returns counters."""
    if provider not in _PARSERS:
        raise ValueError(f"unknown provider {provider!r}")
    parser = _PARSERS[provider]

    captured_at = datetime.now(timezone.utc).isoformat()
    counts = {"fetched": 0, "parsed_ok": 0, "skipped": 0, "written": 0}

    for raw in fetcher.fetch(
        since_iso=since_iso,
        workspace_slug=workspace_slug,
        workspace_id=workspace_id,
    ):
        counts["fetched"] += 1
        result = parser(raw, captured_at=captured_at)
        if result.result == "ok" and result.outcome is not None:
            counts["parsed_ok"] += 1
            if apply:
                outcomes_store.write(result.outcome)
                counts["written"] += 1
            else:
                print(f"  [dry-run] would write {result.outcome.id} "
                      f"metric={result.outcome.metric}")
        else:
            counts["skipped"] += 1

    return counts


# ============================================================
# CLI
# ============================================================


def _build_fetcher(provider: str, args) -> EventFetcher:
    if provider == "stripe":
        key = os.environ.get("STRIPE_API_KEY", "")
        if not key:
            raise SystemExit("STRIPE_API_KEY env var required for --provider stripe")
        return StripeFetcher(key)
    if provider == "vercel":
        token = os.environ.get("VERCEL_API_TOKEN", "")
        if not token:
            raise SystemExit("VERCEL_API_TOKEN env var required for --provider vercel")
        if not args.vercel_project_id:
            raise SystemExit("--vercel-project-id required for --provider vercel")
        return VercelFetcher(token, args.vercel_project_id)
    if provider == "linear":
        key = os.environ.get("LINEAR_API_KEY", "")
        if not key:
            raise SystemExit("LINEAR_API_KEY env var required for --provider linear")
        return LinearFetcher(key)
    raise SystemExit(f"unknown provider {provider!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus_backfill")
    parser.add_argument("--provider", required=True,
                        choices=list(_PARSERS.keys()))
    parser.add_argument("--workspace", required=True,
                        help="workspace slug (e.g. acme)")
    parser.add_argument("--workspace-id", required=True,
                        help="workspace id (e.g. ws-1)")
    parser.add_argument("--since", default=None,
                        help="ISO date (default: 30 days ago)")
    parser.add_argument("--apply", action="store_true",
                        help="actually write outcomes (default: dry-run)")
    parser.add_argument("--vercel-project-id", default=None,
                        help="required when --provider vercel")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.since is None:
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=DEFAULT_SINCE_DAYS)
        args.since = since.isoformat()
    else:
        # Allow date-only; promote to UTC midnight.
        try:
            datetime.fromisoformat(args.since)
        except ValueError:
            args.since = f"{args.since}T00:00:00+00:00"

    outcomes_store = outcomes_store_factory(
        url=os.environ.get("NEXT_PUBLIC_SUPABASE_URL"),
        service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
    )
    fetcher = _build_fetcher(args.provider, args)

    log.info(
        "backfill provider=%s workspace=%s since=%s apply=%s",
        args.provider, args.workspace, args.since, args.apply,
    )

    try:
        counts = backfill(
            provider=args.provider,
            workspace_slug=args.workspace,
            workspace_id=args.workspace_id,
            since_iso=args.since,
            fetcher=fetcher,
            outcomes_store=outcomes_store,
            apply=args.apply,
        )
    except urllib.error.HTTPError as exc:
        log.error("provider API error: %s", exc)
        return 2
    except urllib.error.URLError as exc:
        log.error("network error: %s", exc)
        return 2

    log.info("backfill complete: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
