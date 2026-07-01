"""Autonomy-ladder tool-call gate (RA-6874).

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
"""
from __future__ import annotations

import re
from typing import Any, Optional

TIER_READ = 0          # L0 — read-only / advise
TIER_LOCAL = 1         # L1 — reversible single-domain act
TIER_OUTWARD = 2       # L2 — cross-domain / outward-facing, still reversible
TIER_IRREVERSIBLE = 3  # L3 — irreversible / strategic — STOP for human/Board

# --- Tier 0: read-only ------------------------------------------------------
_READ_ONLY_TOOLS = {
    "Read", "Grep", "Glob", "WebFetch", "WebSearch", "NotebookRead",
    "ListMcpResourcesTool", "ReadMcpResourceTool", "TaskList", "TaskGet",
}
_READ_ONLY_BASH = re.compile(
    r"^\s*(cat|ls|pwd|echo|grep|rg|find|head|tail|wc|which|stat|"
    r"git\s+(status|log|diff|show|branch|remote|fetch|rev-parse|ls-files|ls-tree)|"
    r"gh\s+pr\s+(view|checks|list|diff)|gh\s+(issue|run)\s+(view|list))\b"
)

# --- Tier 3: irreversible / strategic ---------------------------------------
# Precise bash signatures — narrow enough that an L2 feat/* push or PR-open does
# NOT match. Order-independent; any match => L3.
_L3_BASH = [
    r"\bgit\s+merge\b",                                              # merge (esp. to main)
    r"\bgh\s+pr\s+merge\b",                                          # PR merge to base
    r"\bgit\s+push\b[^\n]*\b(origin\s+)?(main|master|prod|production)\b",  # push to main/prod
    r"\bgit\s+push\b[^\n]*--force[^\n]*\b(main|master)\b",           # force-push main
    r"\bvercel\b[^\n]*(--prod|\bpromote\b)",                         # prod deploy / promote
    r"\bvercel\s+deploy\b",                                          # deploy (prod by default)
    r"\bsupabase\s+db\s+push\b",                                     # prod DB migration
    r"\bprisma\s+migrate\s+deploy\b",
    r"\bsupabase\s+migration\s+up\b",
    r"\bgh\s+secret\s+set\b",                                        # secret rotation
    r"\bvercel\s+env\s+(add|rm|remove)\b",                           # env-secret write
    r">>?\s*(?!\S*\.env\.example)\S*\.env(\.[a-z]+)?\b",             # write to a real .env
    r"\bvercel\s+project\s+add\b",                                  # new service
    r"\bsupabase\s+projects?\s+create\b",
    r"\bgh\s+repo\s+create\b",
    r"\bgh\s+api\b[^\n]*branches[^\n]*protection",                  # branch-strategy change
]
_L3_BASH_RE = re.compile("|".join(_L3_BASH), re.IGNORECASE)

# Non-Bash tool-name signatures (MCP + built-ins) that are inherently L3.
_L3_TOOL_RE = re.compile(
    r"(deploy_to_vercel|apply_migration|deploy_edge_function|create_project"
    r"|pause_project|restore_project|delete_branch|merge_branch|db_push)",
    re.IGNORECASE,
)
# Destructive/strategic verbs in an otherwise-unknown tool name -> unsure => higher.
_L3_VERB_RE = re.compile(r"(rotate|charge|payout|transfer|drop_)", re.IGNORECASE)

# --- Tier 2: cross-domain / outward-facing (reversible) ---------------------
_L2_BASH = re.compile(
    r"\bgh\s+pr\s+create\b|"
    r"\bgit\s+push\b(?![^\n]*\b(main|master|prod|production)\b)"
)


def classify(tool_name: str, tool_input: Optional[dict[str, Any]]) -> int:
    """Return the autonomy tier (0-3) for a pending tool call.

    Decision rule (autonomy-ladder): rate by reversibility x domain breadth; the
    HIGHER wins; when genuinely unsure between two tiers, take the higher.
    """
    tool_input = tool_input or {}
    name = tool_name or ""

    # Tool-name L3 (MCP prod deploys / migrations / destructive verbs) — first.
    if _L3_TOOL_RE.search(name) or _L3_VERB_RE.search(name):
        return TIER_IRREVERSIBLE

    if name == "Bash":
        cmd = str(tool_input.get("command", ""))
        if _L3_BASH_RE.search(cmd):
            return TIER_IRREVERSIBLE
        if _READ_ONLY_BASH.search(cmd):
            return TIER_READ
        if _L2_BASH.search(cmd):
            return TIER_OUTWARD
        return TIER_LOCAL

    if name in _READ_ONLY_TOOLS:
        return TIER_READ

    if name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return TIER_LOCAL

    # Unknown tools default to L1 (local/reversible) — do NOT over-block, the
    # destructive-verb guard above already lifts the dangerous ones to L3.
    return TIER_LOCAL


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
