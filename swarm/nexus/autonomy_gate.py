"""Autonomy-ladder tool-call gate (RA-6874, converged in RA-6882).

Classifies a pending Claude Code tool call to an autonomy tier (L0-L3) per the
``autonomy-ladder`` skill and decides whether it may proceed autonomously.

Only genuine **L3** (irreversible / strategic) actions are blocked; L0-L2 pass
through untouched so the normal permission flow and the autonomous loop are
unaffected. A HARD_STOP (``~/.claude/HARD_STOP`` / ``/panic``) denies EVERY tool
call at EVERY tier.

This closes the enforcement gap that ``swarm/nexus/policy.py`` leaves open:
``policy.py`` gates only *pre-stamped* structured actions, not raw tool calls
inside a ``bypassPermissions`` generator turn. The ``PreToolUse`` hook
(``.claude/hooks/autonomy_gate_hook.py``) is the thin stdin/stdout wrapper around
these pure functions — it performs no actions itself.

RA-6882: the tier constants, signature registry, and :func:`classify` now live in
``swarm.nexus.autonomy_ladder`` — the single source of truth shared with the
SDK-loop gate ``app/server/tool_gate.py``. This module keeps only its *disposition*
(interactive surface: deny tier == L3, pass L0-L2 to the human). The SDK gate's
default-deny allowlist is a deliberately different disposition over the same
classifier (see the ladder module docstring and the RA-6882 spec).
"""
from __future__ import annotations

from typing import Any, Optional

from swarm.nexus.autonomy_ladder import (
    TIER_IRREVERSIBLE,
    TIER_LOCAL,
    TIER_OUTWARD,
    TIER_READ,
    classify,
)

__all__ = [
    "TIER_READ", "TIER_LOCAL", "TIER_OUTWARD", "TIER_IRREVERSIBLE",
    "classify", "decide",
]


def decide(
    tool_name: str,
    tool_input: Optional[dict[str, Any]],
    hard_stop: bool = False,
) -> Optional[dict]:
    """Decide a PreToolUse call. ``None`` => pass through (normal perms apply);
    a dict => a deny decision the hook serialises for Claude Code."""
    if hard_stop:
        return _deny(
            "HARD_STOP active (/panic) — every tool call is halted. Remove "
            "~/.claude/HARD_STOP to resume."
        )
    if classify(tool_name, tool_input) >= TIER_IRREVERSIBLE:
        return _deny(
            "Blocked by the autonomy-ladder gate: this is an L3 "
            "(irreversible / strategic) action — e.g. merge/deploy to prod, a "
            "prod DB migration, secret rotation, provisioning a new service, or a "
            "branch-strategy change. L3 must not be self-authorized; it requires "
            "explicit human/Board approval. A human can perform it directly."
        )
    return None


def _deny(reason: str) -> dict:
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}
