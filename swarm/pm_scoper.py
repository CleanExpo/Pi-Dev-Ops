"""swarm/pm_scoper.py — Senior PM Scoping Bot.

Closes the autonomy gap identified by Margot's Board 2026-05-14
deliberation: tickets sitting in Backlog with
`pi-dev:blocked-reason:ambiguous-spec` because no agent polls for them.

RA-2232 sat 4 days unattended because of this gap. The Scoper bot picks
up any such ticket daily, runs grounded Gemini research to produce a
concrete spec, posts it as a Linear comment, removes the ambiguous-spec
label and adds `agent-ready` so `feature_orchestrator` picks it up next
cycle.

Structural pattern mirrors `feature_orchestrator.py` and
`fix_orchestrator.py` — same logging tag shape, same state JSONL,
same `run_cycle()` + `should_run()` shape.

Public API:
    run_cycle(*, dry_run=False) -> ScoperResult
    should_run(state) -> bool

Designed to run as a daily LaunchAgent cron (separate from the busier
60s pollers — ambiguous specs accumulate slowly).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.pm_scoper")

STATE_PATH = Path(os.environ.get(
    "TAO_PM_SCOPER_STATE",
    str(Path.home() / "Pi-CEO" / "Pi-Dev-Ops" / ".harness" / "swarm" / "pm_scoper.jsonl"),
))

# Hermes-style "should_run" cadence — defaults to 12h between cycles
CYCLE_MIN_INTERVAL_S = int(os.environ.get("TAO_PM_SCOPER_INTERVAL_S", str(12 * 60 * 60)))
MAX_TICKETS_PER_CYCLE = int(os.environ.get("TAO_PM_SCOPER_MAX", "3"))

AMBIGUOUS_LABEL = "pi-dev:blocked-reason:ambiguous-spec"
AGENT_READY_LABEL = "agent-ready"
SCOPED_BY_BOT_LABEL = "scoped-by-pm-bot"

LINEAR_API = "https://api.linear.app/graphql"


@dataclass
class ScopedTicket:
    identifier: str               # e.g. "RA-2232"
    title: str
    url: str
    research_summary: str         # what Gemini produced
    citations_count: int
    posted_comment_id: str | None
    labels_added: list[str]
    labels_removed: list[str]


@dataclass
class ScoperResult:
    tickets_seen: int = 0
    tickets_scoped: int = 0
    errors: list[str] = field(default_factory=list)
    scoped: list[ScopedTicket] = field(default_factory=list)
    dry_run: bool = False
    skipped_reason: str | None = None


# ── Linear GraphQL ──────────────────────────────────────────────────────────
def _linear_gql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        LINEAR_API, data=body, method="POST",
        headers={
            "Authorization": os.environ["LINEAR_API_KEY"],
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = json.loads(r.read())
    if "errors" in raw:
        raise RuntimeError(f"Linear GQL errors: {raw['errors']}")
    return raw["data"]


def fetch_ambiguous_tickets(*, limit: int) -> list[dict]:
    """Pull issues currently labelled with the ambiguous-spec marker."""
    data = _linear_gql(
        """query($limit: Int!, $label: String!) {
            issues(
                first: $limit,
                filter: {
                    labels: {name: {eq: $label}},
                    state: {type: {eq: "backlog"}}
                },
                orderBy: createdAt
            ) {
                nodes {
                    id identifier title url createdAt
                    description
                    team { id key name }
                    labels { nodes { id name } }
                    assignee { name email }
                }
            }
        }""",
        {"limit": limit, "label": AMBIGUOUS_LABEL},
    )
    return data["issues"]["nodes"]


def _label_id_for(team_id: str, name: str) -> str | None:
    data = _linear_gql(
        """query($teamId: String!) {
            team(id: $teamId) { labels { nodes { id name } } }
        }""",
        {"teamId": team_id},
    )
    for n in data["team"]["labels"]["nodes"]:
        if n["name"] == name:
            return n["id"]
    return None


def _create_label(team_id: str, name: str, color: str = "#3F7DE2") -> str:
    data = _linear_gql(
        """mutation($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) { issueLabel { id } }
        }""",
        {"input": {"teamId": team_id, "name": name, "color": color}},
    )
    return data["issueLabelCreate"]["issueLabel"]["id"]


def _ensure_label(team_id: str, name: str) -> str:
    lid = _label_id_for(team_id, name)
    return lid or _create_label(team_id, name)


def update_labels(issue_id: str, *, add: list[str], remove: list[str]) -> None:
    if add:
        _linear_gql(
            """mutation($id: String!, $labelIds: [String!]!) {
                issueAddLabels(id: $id, labelIds: $labelIds) { success }
            }""",
            {"id": issue_id, "labelIds": add},
        )
    if remove:
        _linear_gql(
            """mutation($id: String!, $labelIds: [String!]!) {
                issueRemoveLabels(id: $id, labelIds: $labelIds) { success }
            }""",
            {"id": issue_id, "labelIds": remove},
        )


def post_comment(issue_id: str, body: str) -> str:
    data = _linear_gql(
        """mutation($input: CommentCreateInput!) {
            commentCreate(input: $input) { comment { id } }
        }""",
        {"input": {"issueId": issue_id, "body": body}},
    )
    return data["commentCreate"]["comment"]["id"]


# ── Research — Gemini grounded ──────────────────────────────────────────────
def _run_grounded_research(ticket: dict) -> tuple[str, int]:
    """Call existing swarm.research.gemini_research with the ticket as the topic.

    Returns (markdown_summary, citation_count). Falls back to a no-research
    template if the research module is unavailable.
    """
    try:
        # Reuse the existing grounded-research module — already proven on
        # IICRC S500 queries (24 real citations) and Margot's daily briefs.
        from swarm.research import gemini_research  # type: ignore[import-not-found]
    except Exception as e:  # noqa: BLE001
        log.warning("gemini_research unavailable; emitting template only: %s", e)
        return _template_only_spec(ticket), 0

    prompt = (
        f"Concrete specification for Linear ticket {ticket['identifier']}: "
        f"\"{ticket['title']}\".\n\n"
        f"Original ambiguous description:\n{(ticket.get('description') or '(no description)').strip()}\n\n"
        f"Produce: (1) the 1-paragraph problem statement in concrete terms, "
        f"(2) 3–5 acceptance criteria as bullet points, (3) the implementation "
        f"approach in 2–4 sentences, (4) any open questions that still block "
        f"shipping. Format as Markdown. Cite sources for any external facts."
    )

    try:
        import asyncio
        result = asyncio.run(gemini_research.grounded_research(
            prompt, depth="standard", topic=ticket["identifier"],
        ))
        citations_block = ""
        if hasattr(result, "citations") and result.citations:
            citations_block = "\n\n---\n\n**Sources cited:**\n" + "\n".join(
                f"- [{c.title}]({c.url})" for c in result.citations[:8]
            )
        return result.text + citations_block, len(getattr(result, "citations", []) or [])
    except Exception as e:  # noqa: BLE001
        log.warning("grounded_research failed; emitting template only: %s", e)
        return _template_only_spec(ticket), 0


def _template_only_spec(ticket: dict) -> str:
    """Fallback spec when Gemini is unavailable — still useful for triage."""
    return (
        f"## PM Scoper auto-spec for {ticket['identifier']}\n\n"
        f"_Auto-generated by `swarm.pm_scoper` (template fallback — grounded research unavailable)._\n\n"
        f"**Original title:** {ticket['title']}\n\n"
        f"**Problem statement:** _Needs human refinement — research module unavailable._\n\n"
        f"**Acceptance criteria:**\n"
        f"1. Concrete behaviour described as a user story (Given/When/Then)\n"
        f"2. Tests defined for the happy path\n"
        f"3. Linked PR closes the ticket\n\n"
        f"**Implementation approach:** Specialist agent reviews this scope before claiming.\n\n"
        f"**Open questions:** None auto-detected — request review.\n"
    )


# ── State persistence ───────────────────────────────────────────────────────
def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_run_ts": 0, "scoped_identifiers": []}
    try:
        for line in STATE_PATH.read_text().splitlines():
            if line.strip():
                last = json.loads(line)
        return last
    except Exception:  # noqa: BLE001
        return {"last_run_ts": 0, "scoped_identifiers": []}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a") as f:
        f.write(json.dumps(state) + "\n")


def should_run(state: dict | None = None) -> bool:
    state = state or _load_state()
    last = state.get("last_run_ts", 0)
    return (datetime.now(timezone.utc).timestamp() - last) >= CYCLE_MIN_INTERVAL_S


# ── Public API ──────────────────────────────────────────────────────────────
def run_cycle(*, dry_run: bool = False) -> ScoperResult:
    state = _load_state()
    if not should_run(state) and not dry_run:
        return ScoperResult(skipped_reason="cycle-cooldown")

    result = ScoperResult(dry_run=dry_run)
    try:
        tickets = fetch_ambiguous_tickets(limit=MAX_TICKETS_PER_CYCLE)
    except Exception as e:  # noqa: BLE001
        log.exception("fetch_ambiguous_tickets failed")
        result.errors.append(f"fetch: {e}")
        return result

    result.tickets_seen = len(tickets)
    previously_scoped = set(state.get("scoped_identifiers", []))

    for ticket in tickets:
        ident = ticket["identifier"]
        if ident in previously_scoped:
            log.info("skipping %s — already scoped (prevents loop)", ident)
            continue

        try:
            summary, citation_count = _run_grounded_research(ticket)
            comment_body = (
                f"## PM Scoper auto-spec\n\n"
                f"_Generated by `swarm.pm_scoper` at "
                f"{datetime.now(timezone.utc).isoformat()} — "
                f"removes `{AMBIGUOUS_LABEL}` and adds `{AGENT_READY_LABEL}` so "
                f"`feature_orchestrator` picks this up next cycle._\n\n"
                f"{summary}\n"
            )

            comment_id = None
            labels_added: list[str] = []
            labels_removed: list[str] = []

            if not dry_run:
                comment_id = post_comment(ticket["id"], comment_body)
                team_id = ticket["team"]["id"]
                # Add agent-ready + scoped-by-pm-bot, remove ambiguous-spec
                ar_id = _ensure_label(team_id, AGENT_READY_LABEL)
                sb_id = _ensure_label(team_id, SCOPED_BY_BOT_LABEL)
                ambig_id = _label_id_for(team_id, AMBIGUOUS_LABEL)
                update_labels(
                    ticket["id"],
                    add=[ar_id, sb_id],
                    remove=[ambig_id] if ambig_id else [],
                )
                labels_added = [AGENT_READY_LABEL, SCOPED_BY_BOT_LABEL]
                labels_removed = [AMBIGUOUS_LABEL]
                state.setdefault("scoped_identifiers", []).append(ident)

            result.scoped.append(ScopedTicket(
                identifier=ident, title=ticket["title"], url=ticket["url"],
                research_summary=summary, citations_count=citation_count,
                posted_comment_id=comment_id,
                labels_added=labels_added, labels_removed=labels_removed,
            ))
            result.tickets_scoped += 1
            log.info("scoped %s (citations=%d)", ident, citation_count)

        except Exception as e:  # noqa: BLE001
            log.exception("scoping %s failed", ident)
            result.errors.append(f"{ident}: {e}")

    state["last_run_ts"] = datetime.now(timezone.utc).timestamp()
    if not dry_run:
        _save_state(state)
    return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import sys
    dry = "--dry-run" in sys.argv
    r = run_cycle(dry_run=dry)
    print(json.dumps({
        "tickets_seen": r.tickets_seen,
        "tickets_scoped": r.tickets_scoped,
        "errors": r.errors,
        "skipped_reason": r.skipped_reason,
        "scoped": [
            {"id": s.identifier, "title": s.title, "citations": s.citations_count}
            for s in r.scoped
        ],
        "dry_run": r.dry_run,
    }, indent=2))
