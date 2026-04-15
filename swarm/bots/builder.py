"""
swarm/bots/builder.py — RA-650-C: Builder Bot.

Responsibilities:
  - Scan Linear for Urgent/High Todo tickets eligible for autonomous builds
  - Use Ollama to assess each ticket and draft a build brief
  - In shadow mode: log drafts to .harness/swarm/builder.jsonl, send Telegram
    summary — NO calls to /api/build
  - In active mode (Week 3+, board sign-off): authenticate against Pi-Dev-Ops
    and POST /api/build for each eligible ticket

Eligibility rules (applied in shadow mode too — determines what WOULD run):
  1. Priority Urgent (1) or High (2)
  2. State = Todo (not already In Progress or Done)
  3. Has a description long enough to generate a meaningful brief (>50 chars)
  4. Matches a known project → repo URL mapping
  5. Not already queued in this cycle (max MAX_DRAFTS_PER_CYCLE)

Shadow mode is the safe default.  Active mode requires TAO_SWARM_SHADOW=0
plus explicit board sign-off on Phase 2 activation.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from typing import Optional

from .. import config
from ..ollama_client import chat
from ..telegram_alerts import send

log = logging.getLogger("swarm.builder")

MAX_DRAFTS_PER_CYCLE = 2  # Cap: never queue more than 2 builds per cycle

# Known project → GitHub repo mapping.
# Builder only processes tickets from projects it knows the repo for.
PROJECT_REPO_MAP: dict[str, str] = {
    "Pi - Dev -Ops":               "https://github.com/CleanExpo/Pi-Dev-Ops",
    "Billing & Estimation Platform v2": "https://github.com/CleanExpo/restore-assist",
}

SYSTEM_PROMPT = """You are Builder — the autonomous coding agent for the Pi-CEO swarm.

Your role:
1. Assess whether a Linear ticket is eligible for an autonomous build session
2. If eligible, write a concise, actionable build brief (2-4 sentences max)
3. The brief must describe WHAT to implement, not WHY — it goes directly into a Claude coding session

Eligibility criteria:
- Has a clear, specific technical task (not a discussion, meeting, or research ticket)
- Scope is narrow enough for a single session (not a full epic)
- Description contains enough detail to implement without human clarification

Always respond in JSON with this exact structure:
{
  "eligible": true|false,
  "reason": "one sentence",
  "brief": "2-4 sentence implementation brief (null if not eligible)",
  "estimated_complexity": "basic|detailed|advanced"
}"""


def _fetch_buildable_tickets(api_key: str) -> list[dict]:
    """Fetch Urgent/High Todo tickets with known project-repo mappings from Linear.

    Returns list of {id, title, description, project, priority} dicts.
    Returns empty list on any error.
    """
    if not api_key:
        return []

    # Filter by priority + state + team; project filtering done in Python after fetch
    query = """
    query {
      issues(
        filter: {
          state: { type: { in: ["unstarted"] } }
          priority: { lte: 2 }
          team: { name: { eq: "RestoreAssist" } }
        }
        first: 20
        orderBy: updatedAt
      ) {
        nodes {
          identifier
          title
          description
          priority
          project { name }
          state { name }
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
        results = []
        for i in issues:
            project_name = (i.get("project") or {}).get("name", "")
            # Only include tickets whose project has a known repo mapping
            if project_name not in PROJECT_REPO_MAP:
                continue
            # Must have a real description (>50 chars) to generate a meaningful brief
            if len((i.get("description") or "")) <= 50:
                continue
            results.append({
                "id": i["identifier"],
                "title": i["title"],
                "description": (i.get("description") or "")[:800],
                "priority": i.get("priority", 3),
                "project": project_name,
                "state": (i.get("state") or {}).get("name", "Todo"),
            })
        return results
    except Exception as exc:
        log.warning("Builder: Linear fetch failed: %s", exc)
        return []


def _assess_ticket(ticket: dict) -> dict:
    """Ask Ollama to assess build eligibility and draft a brief for a ticket.

    Returns parsed LLM dict with keys: eligible, reason, brief, estimated_complexity.
    Returns safe defaults on any error.
    """
    prompt = (
        f"Ticket: {ticket['id']} — {ticket['title']}\n"
        f"Priority: {ticket['priority']} | Project: {ticket['project']}\n\n"
        f"Description:\n{ticket['description']}"
    )
    response = chat(
        model=config.BOT_MODELS["builder"],
        system=SYSTEM_PROMPT,
        user_message=prompt,
        temperature=0.1,
        json_format=True,
    )
    if not response:
        return {"eligible": False, "reason": "LLM unavailable", "brief": None, "estimated_complexity": "basic"}
    try:
        return json.loads(response)
    except Exception:
        return {"eligible": False, "reason": "LLM parse error", "brief": None, "estimated_complexity": "basic"}


def _fire_build(ticket_id: str, repo_url: str, brief: str, complexity: str) -> Optional[str]:
    """POST to /api/build and return session_id.  Only called in active mode.

    Returns session_id string on success, None on any error.
    """
    base = config.PIDEVOPS_BASE_URL.rstrip("/")
    password = config.PIDEVOPS_PASSWORD
    if not password:
        log.warning("Builder: PIDEVOPS_PASSWORD not set — cannot fire build")
        return None

    # Step 1: login to get session cookie
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    login_payload = json.dumps({"password": password}).encode()
    login_req = urllib.request.Request(
        f"{base}/api/login",
        data=login_payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(login_req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        log.warning("Builder: login failed: %s", exc)
        return None

    # Step 2: POST /api/build
    tier_map = {"basic": "basic", "detailed": "detailed", "advanced": "advanced"}
    build_payload = json.dumps({
        "repo_url": repo_url,
        "brief": f"[RA-650 Builder — {ticket_id}] {brief}",
        "model": "sonnet",
        "complexity_tier": tier_map.get(complexity, ""),
        "intent": f"swarm_builder:{ticket_id}",
    }).encode()
    build_req = urllib.request.Request(
        f"{base}/api/build",
        data=build_payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(build_req, timeout=15) as resp:
            data = json.loads(resp.read())
        session_id = data.get("session_id", "")
        log.info("Builder: session %s started for %s", session_id, ticket_id)
        return session_id
    except Exception as exc:
        log.warning("Builder: /api/build failed for %s: %s", ticket_id, exc)
        return None


def _log_cycle(entry: dict) -> None:
    """Append a Builder observation to the JSONL log."""
    log_file = config.SWARM_LOG_DIR / "builder.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _read_pr_counter() -> dict:
    """Read today's autonomous-PR counter from pr_rate_limit.json.

    Resets automatically when the date changes.
    """
    counter_file = config.SWARM_LOG_DIR / "pr_rate_limit.json"
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        with open(counter_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != today:
            return {"date": today, "count": 0, "limit": config.MAX_AUTONOMOUS_PRS_PER_DAY}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": today, "count": 0, "limit": config.MAX_AUTONOMOUS_PRS_PER_DAY}


def _increment_pr_counter(counter: dict) -> None:
    """Atomically persist incremented PR counter (write-tmp→replace)."""
    counter_file = config.SWARM_LOG_DIR / "pr_rate_limit.json"
    counter["count"] += 1
    counter["limit"] = config.MAX_AUTONOMOUS_PRS_PER_DAY
    tmp_path = str(counter_file) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(counter, f)
    os.replace(tmp_path, str(counter_file))


def run_cycle(unacked_count: int) -> dict:
    """Execute one Builder observation cycle.

    Shadow mode: assess tickets, draft build sessions, log and report.
    Active mode: assess tickets and fire /api/build for eligible ones.

    Args:
        unacked_count: Current unacked iteration count from orchestrator.

    Returns:
        Dict with keys: eligible_count, fired_count, shadow_mode, drafts.
    """
    api_key = os.environ.get("LINEAR_API_KEY", "")

    tickets = _fetch_buildable_tickets(api_key)
    log.debug("Builder: %d buildable tickets fetched", len(tickets))

    drafts: list[dict] = []
    fired: list[dict] = []

    for ticket in tickets:
        if len(drafts) >= MAX_DRAFTS_PER_CYCLE:
            break

        assessment = _assess_ticket(ticket)
        if not assessment.get("eligible"):
            log.debug("Builder: %s not eligible — %s", ticket["id"], assessment.get("reason"))
            continue

        repo_url = PROJECT_REPO_MAP.get(ticket["project"], "")
        if not repo_url:
            log.debug("Builder: no repo mapping for project %s", ticket["project"])
            continue

        draft = {
            "ticket_id": ticket["id"],
            "title": ticket["title"],
            "project": ticket["project"],
            "repo_url": repo_url,
            "brief": assessment.get("brief", ""),
            "complexity": assessment.get("estimated_complexity", "basic"),
            "reason": assessment.get("reason", ""),
            "session_id": None,
        }
        drafts.append(draft)

        if not config.SHADOW_MODE:
            # Active mode: check daily PR rate limit before firing
            pr_counter = _read_pr_counter()
            if pr_counter["count"] >= config.MAX_AUTONOMOUS_PRS_PER_DAY:
                log.warning(
                    "Builder: daily PR limit reached (%d/%d) — skipping %s",
                    pr_counter["count"], config.MAX_AUTONOMOUS_PRS_PER_DAY, ticket["id"],
                )
                send(
                    message=(
                        f"<b>Builder: daily PR limit reached</b>\n"
                        f"{pr_counter['count']}/{config.MAX_AUTONOMOUS_PRS_PER_DAY} PRs today — "
                        f"{ticket['id']} queued for tomorrow."
                    ),
                    severity="info",
                    bot_name="Builder",
                )
                break

            session_id = _fire_build(
                ticket_id=ticket["id"],
                repo_url=repo_url,
                brief=assessment.get("brief", ticket["title"]),
                complexity=assessment.get("estimated_complexity", "basic"),
            )
            draft["session_id"] = session_id
            if session_id:
                fired.append(draft)
                _increment_pr_counter(pr_counter)

    result: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tickets_scanned": len(tickets),
        "eligible_count": len(drafts),
        "fired_count": len(fired),
        "shadow_mode": config.SHADOW_MODE,
        "drafts": drafts,
    }

    _log_cycle(result)

    if config.SHADOW_MODE:
        if drafts:
            draft_lines = [
                f"• [{d['ticket_id']}] {d['title'][:60]} → <i>{d['complexity']}</i>"
                for d in drafts
            ]
            send(
                message=(
                    f"<b>Builder Shadow Report</b>\n\n"
                    f"Scanned {len(tickets)} tickets → {len(drafts)} would build:\n"
                    + "\n".join(draft_lines)
                    + "\n\n<i>Shadow mode: no sessions started</i>"
                ),
                severity="info",
                bot_name="Builder",
            )
        log.info(
            "Builder cycle (shadow): scanned=%d eligible=%d",
            len(tickets), len(drafts),
        )
    else:
        log.info(
            "Builder cycle (active): scanned=%d eligible=%d fired=%d",
            len(tickets), len(drafts), len(fired),
        )
        if fired:
            fired_lines = [
                f"• [{d['ticket_id']}] session {d['session_id']}"
                for d in fired
            ]
            send(
                message=(
                    f"<b>Builder Active Report</b>\n\n"
                    f"Started {len(fired)} build session(s):\n"
                    + "\n".join(fired_lines)
                ),
                severity="high",
                bot_name="Builder",
            )

    return result
