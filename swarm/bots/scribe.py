"""
swarm/bots/scribe.py — RA-650-D: Scribe Bot.

Responsibilities:
  - Monitor Linear for Urgent/High tickets that need documentation or updates
  - Scan .harness/lessons.jsonl for unprocessed pipeline lessons
  - Draft ticket comments and status updates
  - In shadow mode: log drafts to .harness/swarm/scribe.jsonl, send Telegram
    summary — NO writes to Linear
  - In active mode (Week 3+, board sign-off): execute drafted actions

Shadow mode is the safe default.  Active mode requires TAO_SWARM_SHADOW=0.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..ollama_client import chat
from ..telegram_alerts import send

log = logging.getLogger("swarm.scribe")

SYSTEM_PROMPT = """You are Scribe — the documentation and ticket management bot for the Pi-CEO autonomous swarm.

Your role:
1. Review Linear tickets that have stalled or need updates
2. Identify pipeline lessons that should be documented
3. Draft concise ticket comments or status updates

Always respond in JSON with this exact structure:
{
  "actions": [
    {
      "type": "comment|status_update|create_ticket",
      "ticket_id": "RA-xxx or null for new",
      "draft": "the text you would write",
      "rationale": "one sentence explaining why"
    }
  ],
  "summary": "one sentence describing your overall assessment",
  "lesson_count_processed": 0
}"""


def _fetch_linear_stalled(api_key: str) -> list[dict]:
    """Fetch In Progress tickets not updated in >24h from Linear REST API.

    Returns a list of lightweight ticket dicts: {id, title, state, updatedAt}.
    Returns empty list on any error (fire-and-forget).
    """
    if not api_key:
        return []

    query = """
    query {
      issues(
        filter: {
          state: { type: { in: ["started"] } }
          team: { name: { eq: "RestoreAssist" } }
          priority: { lte: 2 }
          updatedAt: { lt: "-P1D" }
        }
        first: 10
        orderBy: updatedAt
      ) {
        nodes {
          identifier
          title
          state { name }
          updatedAt
          assignee { name }
        }
      }
    }
    """
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        issues = data.get("data", {}).get("issues", {}).get("nodes", [])
        return [
            {
                "id": i["identifier"],
                "title": i["title"],
                "state": i.get("state", {}).get("name", "?"),
                "updated": i.get("updatedAt", "?"),
                "assignee": (i.get("assignee") or {}).get("name", "unassigned"),
            }
            for i in issues
        ]
    except Exception as exc:
        log.warning("Scribe: Linear fetch failed: %s", exc)
        return []


def _read_new_lessons(since_ts: float | None = None) -> list[dict]:
    """Read unprocessed entries from .harness/lessons.jsonl.

    Args:
        since_ts: Only return entries with ts > this unix timestamp.
                  None = return last 5 entries regardless of age.
    """
    lessons_path = Path(config.LESSONS_FILE)
    if not lessons_path.exists():
        return []

    results: list[dict] = []
    try:
        lines = lessons_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines[-20:]):  # check last 20
            try:
                entry = json.loads(line)
                if since_ts:
                    entry_ts = entry.get("ts", 0)
                    if isinstance(entry_ts, str):
                        from datetime import datetime
                        entry_ts = datetime.fromisoformat(entry_ts).timestamp()
                    if entry_ts <= since_ts:
                        continue
                results.append(entry)
                if len(results) >= 5:
                    break
            except Exception:
                continue
    except Exception as exc:
        log.warning("Scribe: lessons read failed: %s", exc)

    return list(reversed(results))


def _log_drafts(entry: dict) -> None:
    """Append a Scribe observation to the JSONL log."""
    log_file = config.SWARM_LOG_DIR / "scribe.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_cycle(unacked_count: int) -> dict:
    """Execute one Scribe observation cycle.

    Checks:
      1. Linear for stalled In Progress tickets (Urgent/High, >24h no update)
      2. .harness/lessons.jsonl for new pipeline lessons to document

    In shadow mode: drafts actions, logs them, notifies Telegram — no writes.
    In active mode: executes drafted actions (Week 3+).

    Args:
        unacked_count: Current unacked iteration count (passed from orchestrator).

    Returns:
        Dict with keys: action_count, shadow_mode, summary, drafts.
    """
    api_key = os.environ.get("LINEAR_API_KEY", "")

    stalled = _fetch_linear_stalled(api_key)
    lessons = _read_new_lessons(since_ts=time.time() - 3600)  # last hour

    # Build assessment context for the LLM
    stalled_text = "\n".join(
        f"- {t['id']}: {t['title']} [{t['state']}] — last updated {t['updated']}"
        for t in stalled
    ) or "None"
    lesson_text = "\n".join(
        f"- {l.get('ts', '?')}: {l.get('lesson', l.get('summary', str(l)[:120]))}"
        for l in lessons
    ) or "None"

    assessment_prompt = (
        f"Stalled In Progress tickets (Urgent/High, no update >24h):\n{stalled_text}\n\n"
        f"New pipeline lessons (last hour):\n{lesson_text}\n\n"
        f"Shadow mode: {config.SHADOW_MODE}\n"
        f"Unacknowledged iterations: {unacked_count}/{config.MAX_UNACKED_ITERATIONS}"
    )

    llm_response = chat(
        model=config.BOT_MODELS["scribe"],
        system=SYSTEM_PROMPT,
        user_message=assessment_prompt,
        temperature=0.2,
        json_format=True,
    )

    # Parse LLM output
    drafts: list[dict] = []
    llm_summary = ""
    if llm_response:
        try:
            llm_data = json.loads(llm_response)
            drafts = llm_data.get("actions", [])
            llm_summary = llm_data.get("summary", "")
        except Exception:
            log.warning("Scribe: LLM JSON parse failed, raw: %s", (llm_response or "")[:200])

    result: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stalled_count": len(stalled),
        "lesson_count": len(lessons),
        "action_count": len(drafts),
        "shadow_mode": config.SHADOW_MODE,
        "summary": llm_summary or f"Scribe cycle: {len(stalled)} stalled tickets, {len(lessons)} new lessons",
        "drafts": drafts,
        "raw_llm": llm_response,
    }

    _log_drafts(result)

    if config.SHADOW_MODE:
        # Shadow mode: log drafts only, no Linear writes
        if drafts:
            draft_lines = [
                f"• [{d.get('ticket_id', 'NEW')}] {d.get('type', '?')}: {d.get('draft', '')[:80]}…"
                for d in drafts[:3]
            ]
            send(
                message=(
                    f"<b>Scribe Shadow Report</b>\n\n"
                    f"{result['summary']}\n\n"
                    f"Drafted (not submitted):\n" + "\n".join(draft_lines)
                ),
                severity="info",
                bot_name="Scribe",
            )
        log.info(
            "Scribe cycle (shadow): stalled=%d lessons=%d drafts=%d",
            len(stalled), len(lessons), len(drafts),
        )
    else:
        # Active mode (Phase 2+) — execute drafts
        log.info("Scribe active mode: %d actions pending Phase 2 implementation", len(drafts))

    return result
