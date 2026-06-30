"""
app/server/tool_gate.py — SDK-layer irreversible-action interceptor.

The autonomous coding loop runs each generator turn under the SDK with tool
execution enabled. The structured reversibility gate (swarm/nexus/policy.py)
only classifies pre-stamped business actions (spend, drafts); it never sees a
destructive *tool call* (rm -rf, prod deploy, DROP TABLE) issued inside a
generator turn. This module closes that hole: a pure, high-precision decision
function consulted by the SDK ``can_use_tool`` callback (see session_sdk).

Design boundary (honours the locked feedback-autonomy memory):
  * Reversible / unrecognised → ALLOW. A coding agent must be able to work; we
    do not block on uncertainty, only on recognised-destructive operations.
  * Recognised-irreversible → deny + escalate. High precision (low false
    positive) by design — this is a denylist of clearly-destructive operations,
    not a general classifier.

Pure: no I/O, no SDK import. The escalation side-effect lives in the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolGateDecision:
    allow: bool
    reversibility: str  # "reversible" | "irreversible"
    reason: str
    label: str = ""     # short tag of the matched rule, for audit/dedup


# Each rule: (label, compiled pattern). Matched against the Bash command text.
# Patterns are deliberately narrow — only operations that destroy state with no
# git/undo path, or that push to a production/external system.
_IRREVERSIBLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Recursive+forced delete (rm -rf, rm -fr, rm -r -f, rm --recursive --force)
    ("rm-rf", re.compile(
        r"\brm\b(?=(?:[^\n]*\s-{1,2}[a-z-]*r))(?=(?:[^\n]*\s-{1,2}[a-z-]*f))",
        re.IGNORECASE)),
    # Force push to a remote
    ("git-force-push", re.compile(
        r"\bgit\s+push\b[^\n]*\s(?:--force\b|--force-with-lease\b|-[a-z]*f)",
        re.IGNORECASE)),
    # Destructive SQL
    ("sql-drop", re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE)),
    ("sql-truncate", re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?\w", re.IGNORECASE)),
    ("sql-delete-no-where", re.compile(
        r"\bDELETE\s+FROM\b(?![\s\S]*\bWHERE\b)", re.IGNORECASE)),
    # Production / external publishing
    ("vercel-prod", re.compile(r"\bvercel\b[^\n]*--prod\b", re.IGNORECASE)),
    ("supabase-db-push", re.compile(r"\bsupabase\s+db\s+push\b", re.IGNORECASE)),
    ("prisma-migrate", re.compile(r"\bprisma\s+migrate\s+(?:deploy|reset)\b", re.IGNORECASE)),
    ("npm-publish", re.compile(r"\bnpm\s+publish\b", re.IGNORECASE)),
    ("gh-release", re.compile(r"\bgh\s+release\s+create\b", re.IGNORECASE)),
    ("terraform", re.compile(r"\bterraform\s+(?:apply|destroy)\b", re.IGNORECASE)),
    ("kubectl-delete", re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE)),
    # Disk / device destruction
    ("mkfs", re.compile(r"\bmkfs\b", re.IGNORECASE)),
    ("dd-to-device", re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE)),
]

_BASH_TOOLS = {"Bash", "bash", "BashOutput"}


def _command_text(tool_name: str, tool_input: dict) -> str:
    """Extract the shell command from a Bash-family tool call; else ''."""
    if tool_name not in _BASH_TOOLS:
        return ""
    cmd = tool_input.get("command", "")
    return cmd if isinstance(cmd, str) else ""


def decide(tool_name: str, tool_input: dict | None) -> ToolGateDecision:
    """Return an allow/deny decision for a single tool call.

    Only Bash-family commands are inspected; all other tools (Read, Edit,
    Write, Grep, …) are allowed — file edits are git-reversible. A recognised
    irreversible command is denied with a founder-facing reason.
    """
    tool_input = tool_input or {}
    cmd = _command_text(tool_name, tool_input)
    if not cmd:
        return ToolGateDecision(True, "reversible", "", "")

    for label, pat in _IRREVERSIBLE_RULES:
        if pat.search(cmd):
            return ToolGateDecision(
                allow=False,
                reversibility="irreversible",
                reason=(
                    f"Blocked irreversible operation ({label}). Per the locked "
                    f"autonomy boundary, destructive/irreversible actions require "
                    f"founder approval and are not auto-run."
                ),
                label=label,
            )

    return ToolGateDecision(True, "reversible", "", "")


__all__ = ["ToolGateDecision", "decide"]
