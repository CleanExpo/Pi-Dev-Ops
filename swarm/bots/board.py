"""swarm/bots/board.py — request-driven Board entry-point for senior bots.

Thin wrapper over ``swarm.board`` that exposes the three trigger surfaces:

1. Senior-bot escalation:
       board_bot.escalate(role, action, justification, snapshots) -> session_id
2. Margot insight:
       board_bot.from_margot(insight, citations) -> session_id
3. Founder request (via Telegram intent):
       board_bot.from_founder(prompt) -> session_id

All three return immediately (non-blocking, persistent-pending pattern).
The orchestrator's per-cycle hook will call ``board.process_pending()``
when wired in a separate ticket.

NOT a per-cycle bot — does not implement run_cycle. The Board is
event-driven, not cyclic.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .. import board as _board

log = logging.getLogger("swarm.bots.board")

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Trigger surfaces ────────────────────────────────────────────────────────


def escalate(*, role: str, action: str, justification: str,
              material_input: str = "",
              requested_decisions: list[str] | None = None,
              repo_root: Path | None = None) -> str:
    """Senior bot escalation. Use when a bot wants to take a strategic
    action above its routine ceiling.

    Returns session_id immediately. Directives flow back via
    ``board.get_directives_for_role(role)`` on subsequent cycles.
    """
    brief = _board.BoardBrief(
        topic=f"{role} escalation: {action}",
        triggered_by="senior-bot",
        triggering_actor=role,
        material_input=(
            material_input
            or f"Justification: {justification}"
        ),
        requested_decisions=(requested_decisions or [
            "Should the bot proceed with this action?",
            "If yes, what constraints / ceilings apply?",
            "If no, what alternative does the Board recommend?",
        ]),
    )
    return _board.request_deliberation(brief, repo_root=repo_root or REPO_ROOT)


def from_margot(*, topic: str, insight: str,
                 citations: list[dict[str, Any]] | None = None,
                 requested_decisions: list[str] | None = None,
                 repo_root: Path | None = None) -> str:
    """Margot research surfaced something material.

    citations: list of {url, retrieved_at, source_tier} dicts (per the
    verifiability contract — Wave 5.6). Embedded into material_input.
    """
    citations = citations or []
    cit_lines = [
        f"- [{c.get('source_tier', 'unknown')}] "
        f"{c.get('url', 'no url')} "
        f"(retrieved {c.get('retrieved_at', 'unknown')})"
        for c in citations
    ]
    material = insight
    if cit_lines:
        material += "\n\nCitations:\n" + "\n".join(cit_lines)

    brief = _board.BoardBrief(
        topic=topic,
        triggered_by="margot",
        triggering_actor="Margot",
        material_input=material,
        requested_decisions=(requested_decisions or [
            "Is this material to current strategy?",
            "What action (if any) should the Board direct?",
            "Does this require founder attention?",
        ]),
    )
    return _board.request_deliberation(brief, repo_root=repo_root or REPO_ROOT)


def from_founder(*, prompt: str, requested_decisions: list[str] | None = None,
                  repo_root: Path | None = None) -> str:
    """Founder explicitly asks the Board to deliberate.

    Surface: Telegram intent ``deliberate: <topic>`` routed via
    intent_router; CoS bot calls this.
    """
    brief = _board.BoardBrief(
        topic=prompt[:120],
        triggered_by="founder",
        triggering_actor="founder",
        material_input=prompt,
        requested_decisions=(requested_decisions or [
            "What does the Board recommend?",
            "What does the Board recommend AGAINST?",
            "What clarifying question does the Board need from the founder?",
        ]),
    )
    return _board.request_deliberation(brief, repo_root=repo_root or REPO_ROOT)


# ── Pending queue inspection (for orchestrator wiring + dashboard) ──────────


def queue_depth(*, repo_root: Path | None = None) -> int:
    return len(_board.get_pending(repo_root=repo_root or REPO_ROOT))


def list_pending(*, repo_root: Path | None = None) -> list[str]:
    return _board.get_pending(repo_root=repo_root or REPO_ROOT)


__all__ = [
    "escalate", "from_margot", "from_founder",
    "queue_depth", "list_pending",
]
