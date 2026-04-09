"""
board_meeting.py — Board Meeting Agent (Managed Agents API PoC)

Creates a cloud-hosted board meeting agent that:
1. Reads Linear project state via MCP
2. Reads Pi-CEO harness state via MCP
3. Runs a structured 6-phase board meeting deliberation
4. Saves minutes to .harness/board-meetings/

This is Phase 1 of the Claude Agent SDK PoC (RA-485).
Uses the Anthropic Managed Agents API (public beta).

Usage:
    python -m app.server.agents.board_meeting [--dry-run]
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from anthropic import Anthropic

log = logging.getLogger("pi-ceo.agents.board-meeting")

ANTI_RUSH_PROTOCOL = """
## EXECUTION DISCIPLINE (NON-NEGOTIABLE)

PACE: Thoroughness over speed. Every task gets the time it needs.
- Before writing ANY code: read the existing codebase in the target area FIRST.
- Before proposing ANY architecture: read existing docs/architecture/ FIRST.
- Before ANY content: check memory for prior patterns FIRST.
- NEVER generate placeholder/TODO code. Every function is complete or not written.
- NEVER skip error handling, loading states, edge cases, or types.
- If unsure about requirements, ASK via ceo_report tool — do not assume.

QUALITY OVER QUANTITY:
- Fewer files with complete, tested code > many files with gaps.
- One fully working feature > three half-working features.
- Ask: "Would I ship this to a paying customer right now?" If no, keep working.
"""

BOARD_MEETING_SYSTEM = f"""You are the Senior Project Manager for Pi-CEO, running an autonomous board meeting.

{ANTI_RUSH_PROTOCOL}

## BOARD MEETING PROTOCOL

You run a structured 6-phase board deliberation:

Phase 1 — STATUS: Read the current Linear board state (all issues, their statuses).
Phase 2 — LINEAR REVIEW: Analyze what was completed, what is blocked, what is next.
Phase 3 — SWOT: Identify Strengths, Weaknesses, Opportunities, Threats for the project.
Phase 4 — SPRINT RECOMMENDATIONS: Propose the next sprint's priorities with rationale.
Phase 5 — SAVE MINUTES: Write structured board meeting minutes.
Phase 6 — UPDATE LINEAR: Create any new tickets identified during deliberation.

## OUTPUT FORMAT

Write board meeting minutes in markdown with:
- Date, cycle number, attendees (agent personas)
- Decisions made (with vote counts)
- Action items with owners and deadlines
- Risk register updates
- Next meeting trigger

## RULES

- Source decisions from actual project data, not assumptions
- Reference specific ticket IDs (RA-xxx) and file paths
- Zero filler language: no delve/tapestry/landscape/leverage/robust/seamless
- Every recommendation must have a concrete rationale
"""


def create_agent(client: Anthropic) -> dict[str, Any]:
    """Create the board-meeting agent definition."""
    agent = client.beta.agents.create(
        name="Pi-CEO Board Meeting",
        model="claude-sonnet-4-6",
        system=BOARD_MEETING_SYSTEM,
        tools=[
            {"type": "agent_toolset_20260401"},
        ],
    )
    log.info("Created agent: id=%s version=%s", agent.id, agent.version)
    return {"id": agent.id, "version": agent.version}


def create_environment(client: Anthropic) -> str:
    """Create a cloud environment with network access for MCP."""
    env = client.beta.environments.create(
        name="pi-ceo-board-meeting",
        config={
            "type": "cloud",
            "networking": {"type": "unrestricted"},
            "setup_commands": [
                "pip install --break-system-packages requests",
            ],
        },
    )
    log.info("Created environment: id=%s", env.id)
    return env.id


def run_board_meeting(
    client: Anthropic,
    agent_id: str,
    environment_id: str,
    cycle: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a single board meeting cycle.

    Returns dict with: session_id, duration_s, events_count, minutes (str).
    """
    now = datetime.now(timezone.utc)
    cycle_num = cycle or int(now.timestamp() // (6 * 3600))
    title = f"Board Meeting — Cycle {cycle_num} — {now.strftime('%Y-%m-%d %H:%M UTC')}"

    log.info("Starting board meeting: %s", title)
    start = time.monotonic()

    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title=title,
    )
    log.info("Session created: id=%s", session.id)

    prompt = f"""Run a board meeting for Pi-CEO (Cycle {cycle_num}).

Current date: {now.strftime('%Y-%m-%d %H:%M UTC')}

Execute all 6 phases of the board meeting protocol:
1. Read project status from the harness files
2. Review Linear board state
3. Run SWOT analysis
4. Generate sprint recommendations
5. Write structured minutes
6. Identify any new tickets needed

The Pi-CEO project is a Zero Touch Engineering platform with:
- FastAPI backend (Railway-deployed)
- Next.js dashboard (Vercel-deployed)
- MCP server for Claude Desktop
- 28 TAO skills
- Currently at ZTE Score 60/60

Focus on: what was shipped recently, what is blocked, what should be next.
"""

    if dry_run:
        log.info("DRY RUN — would send prompt to session %s", session.id)
        return {
            "session_id": session.id,
            "duration_s": 0,
            "events_count": 0,
            "minutes": "[dry run — no execution]",
            "dry_run": True,
        }

    collected_text: list[str] = []
    tools_used: list[str] = []
    events_count = 0

    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": prompt}],
                },
            ],
        )

        for event in stream:
            events_count += 1
            match event.type:
                case "agent.message":
                    for block in event.content:
                        if hasattr(block, "text"):
                            collected_text.append(block.text)
                case "agent.tool_use":
                    tools_used.append(event.name)
                    log.info("Tool: %s", event.name)
                case "session.status_idle":
                    log.info("Session idle — board meeting complete")
                    break

    duration = time.monotonic() - start
    minutes = "".join(collected_text)

    result = {
        "session_id": session.id,
        "cycle": cycle_num,
        "duration_s": round(duration, 1),
        "events_count": events_count,
        "tools_used": tools_used,
        "minutes_length": len(minutes),
        "minutes": minutes,
    }

    log.info(
        "Board meeting complete: cycle=%s duration=%.1fs events=%d tools=%d",
        cycle_num,
        duration,
        events_count,
        len(tools_used),
    )
    return result


def main() -> None:
    """CLI entry point for running a board meeting."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run Pi-CEO board meeting via Managed Agents API")
    parser.add_argument("--dry-run", action="store_true", help="Create session but don't execute")
    parser.add_argument("--cycle", type=int, help="Override cycle number")
    parser.add_argument("--agent-id", help="Reuse existing agent ID")
    parser.add_argument("--env-id", help="Reuse existing environment ID")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        raise SystemExit(1)

    client = Anthropic()

    # Create or reuse agent
    if args.agent_id:
        agent_id = args.agent_id
        log.info("Reusing agent: %s", agent_id)
    else:
        agent_info = create_agent(client)
        agent_id = agent_info["id"]

    # Create or reuse environment
    if args.env_id:
        environment_id = args.env_id
        log.info("Reusing environment: %s", environment_id)
    else:
        environment_id = create_environment(client)

    # Run the meeting
    result = run_board_meeting(
        client=client,
        agent_id=agent_id,
        environment_id=environment_id,
        cycle=args.cycle,
        dry_run=args.dry_run,
    )

    # Print summary
    print(json.dumps({k: v for k, v in result.items() if k != "minutes"}, indent=2))
    if result.get("minutes") and not result.get("dry_run"):
        print("\n--- BOARD MEETING MINUTES ---\n")
        print(result["minutes"])


if __name__ == "__main__":
    main()
