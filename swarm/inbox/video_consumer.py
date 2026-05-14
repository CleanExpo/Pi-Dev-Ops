"""swarm/inbox/video_consumer.py — drain video_production_queue.

The CONSUMER half of the PR-triggered Proof Video pipeline. The webhook
receiver at unite-group/api/webhooks/github builds production briefs and
inserts them into `public.video_production_queue` with status='pending'.
This worker drains the queue.

What it does each cycle:

  1. Pull pending rows from video_production_queue (oldest first, capped
     at MAX_PER_CYCLE).
  2. For each row, atomically mark status='dispatched' to prevent
     concurrent claim by another consumer (only one consumer expected
     today, but cheap insurance).
  3. Persist the full production_brief to filesystem at
     ~/Pi-CEO/Pi-Dev-Ops/.harness/video-briefs/{job_id}.json so the
     Video Agency pipeline can pick it up.
  4. Send a SINGLE-SHOT Telegram ping via @PiCeoMarketingBot to Phill
     (per [[no-repeating-alerts]] — one ping per brief, never per phase).
     The ping carries the brief path + the `claude` invocation hint so
     Phill or a Hermes-triggered Claude session can begin the render.
  5. Record a labelled trace via swarm.training.hf_traces for the
     Q3 PEFT LoRA experiment.

What it does NOT do (deferred):
  - Spawning a Claude Code session directly to run the Video Agency
    pipeline. That's a bigger architectural call — Hermes /goal vs
    claude CLI vs Anthropic Agent SDK direct — that should go through
    ceo-board before commit.
  - Auto-completion + auto-delivery. The bridge is brief → ready-for-render.
    The render-and-deliver loop closes when Phill (or the future autonomous
    spawner) consumes the brief.

Public API:
    tick(dry_run: bool = False) -> dict

Designed as a 60-second LaunchAgent cron — same cadence as intake_router +
provisioner. Idempotent: re-running on a row already moved past 'pending'
is a clean no-op.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.inbox.video_consumer")

AEST = timezone(timedelta(hours=10))
BRIEFS_DIR = Path(os.environ.get(
    "TAO_VIDEO_BRIEFS_DIR",
    str(Path.home() / "Pi-CEO" / "Pi-Dev-Ops" / ".harness" / "video-briefs"),
))
MAX_PER_CYCLE = int(os.environ.get("TAO_VIDEO_CONSUMER_MAX", "3"))


# ── Supabase (PostgREST) ────────────────────────────────────────────────────
def _sb_request(method: str, path: str, *, params: dict | None = None,
                body: Any = None, extra_headers: dict | None = None) -> Any:
    url = f"{os.environ['SUPABASE_UNITE_GROUP_URL'].rstrip('/')}/rest/v1{path}"
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    key = os.environ["SUPABASE_UNITE_GROUP_SERVICE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def fetch_pending(*, limit: int) -> list[dict]:
    return _sb_request("GET", "/video_production_queue", params={
        "status": "eq.pending",
        "order": "created_at",
        "limit": limit,
        "select": "id,trigger,source_repo,source_pr_number,source_pr_url,"
                  "source_pr_title,source_linear_issue,source_preview_url,"
                  "client_slug,brand_slug,composition_type,channel,"
                  "duration_seconds,production_brief,created_at",
    }) or []


def claim_row(row_id: str) -> bool:
    """Atomic-ish claim — transition pending → dispatched. Returns False if
    another consumer beat us to it (rare but safe to handle)."""
    try:
        result = _sb_request(
            "PATCH",
            "/video_production_queue",
            params={"id": f"eq.{row_id}", "status": "eq.pending"},
            body={"status": "dispatched", "current_phase": "pre-production"},
            extra_headers={"Prefer": "return=representation"},
        )
        return bool(result and len(result) > 0)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return False
        raise


def mark_ready_for_render(row_id: str, brief_path: Path) -> None:
    """Move dispatched → ready-for-render (a new metadata-only state captured
    in the row's metadata jsonb so we don't need a schema change)."""
    _sb_request(
        "PATCH",
        "/video_production_queue",
        params={"id": f"eq.{row_id}"},
        body={
            "current_phase": "ready-for-render",
            "metadata": {
                "brief_filesystem_path": str(brief_path),
                "ready_at": datetime.now(AEST).isoformat(),
            },
        },
        extra_headers={"Prefer": "return=minimal"},
    )


# ── Telegram (reuse swarm.telegram_router if available) ─────────────────────
def _telegram_ping(text: str) -> None:
    try:
        from swarm import telegram_router  # type: ignore[import-not-found]
        # Marketing channel — these are client-deliverable videos
        telegram_router.send(text, channel="marketing", severity="info",
                             bot_name="VideoConsumer")
    except Exception as e:  # noqa: BLE001 — fire-and-forget
        log.warning("Telegram ping failed (non-fatal): %s", e)


# ── HF Traces capture ───────────────────────────────────────────────────────
def _record_trace(row: dict, brief_path: Path) -> None:
    try:
        from swarm.training import hf_traces  # type: ignore[import-not-found]
        hf_traces.record(
            worker="video_consumer",
            task="dispatch_proof_video",
            input_text=row.get("source_pr_title", ""),
            output_text=json.dumps(row.get("production_brief", {}), default=str)[:8000],
            input_context={
                "client_slug": row.get("client_slug"),
                "brand_slug": row.get("brand_slug"),
                "composition_type": row.get("composition_type"),
                "trigger": row.get("trigger"),
                "source_pr_url": row.get("source_pr_url"),
            },
            output_structured={"brief_path": str(brief_path)},
            duration_seconds=row.get("duration_seconds"),
            linear_issue=row.get("source_linear_issue"),
        )
    except Exception as e:  # noqa: BLE001 — trace must never block
        log.warning("hf_traces.record failed (non-fatal): %s", e)


# ── Process one row ─────────────────────────────────────────────────────────
def _process_row(row: dict, *, dry_run: bool) -> tuple[bool, str | None]:
    """Returns (success, error_message_or_None)."""
    job_id = row["production_brief"].get("job_id") or row["id"]

    # 1. Atomic claim
    if not dry_run:
        if not claim_row(row["id"]):
            return False, "another-consumer-already-claimed"

    # 2. Persist the brief to filesystem
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = BRIEFS_DIR / f"{job_id}.json"
    if not dry_run:
        brief_path.write_text(json.dumps(row["production_brief"], indent=2, default=str))

    # 3. Single-shot Telegram alert to Phill
    if not dry_run:
        client = row.get("client_slug", "unknown")
        comp = row.get("composition_type", "video")
        pr_url = row.get("source_pr_url", "—")
        msg = (
            f"🎬 New Proof Video brief queued — {client} / {comp}\n"
            f"PR: {pr_url}\n"
            f"Brief: {brief_path}\n\n"
            f"To render, invoke: claude --print \"video-director: read {brief_path} and produce + deliver the full video via the Video Agency pipeline\""
        )
        _telegram_ping(msg)

    # 4. Mark ready-for-render
    if not dry_run:
        mark_ready_for_render(row["id"], brief_path)

    # 5. Capture training trace
    if not dry_run:
        _record_trace(row, brief_path)

    return True, None


# ── Main loop ───────────────────────────────────────────────────────────────
def tick(*, dry_run: bool = False) -> dict:
    try:
        rows = fetch_pending(limit=MAX_PER_CYCLE)
    except Exception as e:  # noqa: BLE001
        log.exception("fetch_pending failed")
        return {"rows_seen": 0, "dispatched": 0, "errors": [f"fetch: {e}"], "dry_run": dry_run}

    dispatched = 0
    errors: list[str] = []
    for row in rows:
        try:
            ok, err = _process_row(row, dry_run=dry_run)
            if ok:
                dispatched += 1
            elif err:
                errors.append(f"{row['id']}: {err}")
        except Exception as e:  # noqa: BLE001
            log.exception("processing row %s failed", row["id"])
            errors.append(f"{row['id']}: {e}")

    return {
        "rows_seen": len(rows),
        "dispatched": dispatched,
        "errors": errors,
        "dry_run": dry_run,
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import sys
    dry = "--dry-run" in sys.argv
    print(json.dumps(tick(dry_run=dry), indent=2, default=str))
