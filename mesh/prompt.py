"""Agent prompt construction for the mesh runner.

Separate from ``runner.py`` because the runner owns the claim/worktree/subprocess
lifecycle, while what the agent is actually *told* is its own concern and its own
failure mode — the one recorded below.

**Why the brief travels with the claim.** An unattended agent cannot read Linear: it
holds no Linear credential and its session has no MCP permission for the Linear tools.
A prompt naming only ``linear_id`` therefore leaves it a choice between guessing what
the ticket asks for and stopping. Measured 2026-09-23: a Mac-mini run of UNI-2744
tried four routes to fetch the ticket (Linear MCP tools — refused for lack of
permission; the Pi-CEO Linear search — wrong project; reading the stored key — blocked
by a credential hook; a scratch API script — needed approval an unattended session
cannot give), found none, and correctly stopped without editing code.

Shipping the ticket's own words inside the claim keeps the execution node
credential-free, which is the property worth protecting. Adding a Linear key to every
node would also have worked and would have been strictly worse.
"""
from __future__ import annotations

_WORK_TAIL = (
    "Make a small, verifiable change, run the repo's gates, and stop. "
    "autogit ships each turn to {branch}."
)


def build_prompt(claim: dict, linear_id: str, branch: str) -> str:
    """Return the prompt for one claim.

    An absent title AND description is NOT treated as a ticket that asked for nothing.
    It returns a refusal instruction, so a silent claim-fetch regression surfaces as a
    stopped run rather than as an agent inventing a change. ``""`` and whitespace count
    as absent — present-but-empty is the shape that slips a naive ``is None`` guard.
    """
    title = (claim.get("title") or "").strip()
    description = (claim.get("description") or "").strip()

    if not title and not description:
        return (
            f"Ticket {linear_id} was claimed but its brief did not arrive with the "
            f"claim. Do not guess what it asks for and do not change any code. "
            f"Report that the brief was missing, and stop."
        )

    parts = [f"Work the Linear ticket {linear_id}."]
    if title:
        parts.append(f"\n\nTitle: {title}")
    if description:
        parts.append(f"\n\nTicket description:\n{description}")
    parts.append("\n\n" + _WORK_TAIL.format(branch=branch))
    return "".join(parts)
