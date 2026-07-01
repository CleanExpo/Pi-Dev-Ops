"""swarm/nexus/autonomy_ladder.py — single source of truth for the autonomy ladder.

RA-6882: two safety gates enforce the autonomy ladder on two disjoint surfaces —

  * ``app/server/tool_gate.py``   — SDK ``can_use_tool`` callback for the *unattended*
    autonomous loop. Posture: **allowlist / default-deny**; Bash inspected against a
    destructive **denylist**.
  * ``swarm/nexus/autonomy_gate.py`` — ``PreToolUse`` hook for the *interactive*
    human-driven CLI. Posture: **denylist of genuine L3**; L0-L2 pass through to the
    normal permission prompt.

Before RA-6882 each gate carried its own copy of the destructive-command regexes and
its own tier logic, so the two drifted independently. This module now owns ALL of it:
the tier constants, the named signature registry (every regex defined ONCE), and the
canonical :func:`classify`. Both gates import from here.

The two gates keep their *different dispositions* on purpose (unattended → default-deny;
human-present → deny-only-L3). That divergence is intentional and documented per RA-6882
acceptance criterion #2 — what is NO LONGER allowed to diverge is the pattern set and the
tier of any given call. :func:`classify` is that shared tier; a parity test asserts both
gates agree on it.

Pure: no I/O, no SDK import.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# --- Tiers (DeepMind AGI→ASI continuum mapped to autonomy-ladder L0-L3) ------
TIER_READ = 0          # L0 — read-only / advise
TIER_LOCAL = 1         # L1 — reversible single-domain act
TIER_OUTWARD = 2       # L2 — cross-domain / outward-facing, still reversible
TIER_IRREVERSIBLE = 3  # L3 — irreversible / strategic — STOP for human/Board

# ===========================================================================
# Signature registry — every destructive/strategic regex defined ONCE.
# Consumers select the named subset they enforce; see the per-gate imports.
# ===========================================================================

# --- Read-only signatures (L0) ---------------------------------------------
READ_ONLY_TOOLS = frozenset({
    "Read", "Grep", "Glob", "WebFetch", "WebSearch", "NotebookRead",
    "ListMcpResourcesTool", "ReadMcpResourceTool", "TaskList", "TaskGet",
})
READ_ONLY_BASH = re.compile(
    r"^\s*(cat|ls|pwd|echo|grep|rg|find|head|tail|wc|which|stat|"
    r"git\s+(status|log|diff|show|branch|remote|fetch|rev-parse|ls-files|ls-tree)|"
    r"gh\s+pr\s+(view|checks|list|diff)|gh\s+(issue|run)\s+(view|list))\b"
)

# --- L2: cross-domain / outward-facing but reversible ----------------------
# A feat/* push or a PR-open — outward but undoable. Explicitly NOT a push to a
# protected branch (that is L3, matched first).
L2_BASH = re.compile(
    r"\bgh\s+pr\s+create\b|"
    r"\bgit\s+push\b(?![^\n]*\b(main|master|prod|production)\b)"
)

# --- L3: strategic / irreversible — Bash signatures ------------------------
# Precise signatures: narrow enough that an L2 feat/* push or PR-open does NOT
# match. Any match => L3. This is the CLI hook's L3 set (interactive surface):
# merge/deploy/migrate/secret/env/provision/branch-strategy — genuine
# "stop for a human/Board" actions, all rare in an interactive session.
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
L3_BASH_RE = re.compile("|".join(_L3_BASH), re.IGNORECASE)

# --- L3: strategic / irreversible — non-Bash tool-name signatures ----------
# MCP + built-in tool names that are inherently L3.
L3_TOOL_RE = re.compile(
    r"(deploy_to_vercel|apply_migration|deploy_edge_function|create_project"
    r"|pause_project|restore_project|delete_branch|merge_branch|db_push)",
    re.IGNORECASE,
)
# Destructive/strategic verbs in an otherwise-unknown tool name -> higher tier.
L3_VERB_RE = re.compile(r"(rotate|charge|payout|transfer|drop_)", re.IGNORECASE)


# ===========================================================================
# SDK-loop destructive denylist (unattended surface).
# The autonomous generator runs default-deny; on top of the shared L3 set above
# it also refuses LOCAL-destructive commands with no undo path (rm -rf, mkfs,
# dd, DROP TABLE, curl|sh, ...). These are tier-L3 by reversibility but the CLI
# hook lets a *present human* handle them via the normal prompt — hence they
# live in the SDK subset, not L3_BASH. See RA-6882 spec §D3.
# ===========================================================================

# Per-segment rules: matched against each shell segment independently.
SEGMENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("rm-rf", re.compile(
        r"\brm\b(?=(?:[^\n]*\s-{1,2}[a-z-]*r))(?=(?:[^\n]*\s-{1,2}[a-z-]*f))",
        re.IGNORECASE)),
    ("find-delete", re.compile(r"\bfind\b[^\n]*\s-delete\b", re.IGNORECASE)),
    ("find-exec-rm", re.compile(r"\bfind\b[^\n]*-exec\s+rm\b", re.IGNORECASE)),
    ("git-force-push", re.compile(
        r"\bgit\s+push\b[^\n]*\s(?:--force\b|--force-with-lease\b|-[a-z]*f\b|\+[\w./-]+)",
        re.IGNORECASE)),
    ("sql-drop", re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE)),
    ("sql-truncate", re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?\w", re.IGNORECASE)),
    ("sql-delete-no-where", re.compile(
        r"\bDELETE\s+FROM\b(?![\s\S]*\bWHERE\b)", re.IGNORECASE)),
    ("vercel-prod", re.compile(r"\bvercel\b[^\n]*--prod\b", re.IGNORECASE)),
    ("supabase-db-push", re.compile(r"\bsupabase\s+db\s+push\b", re.IGNORECASE)),
    ("prisma-migrate", re.compile(r"\bprisma\s+migrate\s+(?:deploy|reset)\b", re.IGNORECASE)),
    ("npm-publish", re.compile(r"\bnpm\s+publish\b", re.IGNORECASE)),
    ("gh-release", re.compile(r"\bgh\s+release\s+create\b", re.IGNORECASE)),
    ("terraform", re.compile(r"\bterraform\s+(?:apply|destroy)\b", re.IGNORECASE)),
    ("kubectl-delete", re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE)),
    ("mkfs", re.compile(r"\bmkfs\b", re.IGNORECASE)),
    ("dd-to-device", re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE)),
]

# Whole-command rules: inherently cross-segment (a pipe IS the payload).
WHOLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("pipe-to-shell", re.compile(
        r"(?:curl|wget|fetch|base64)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE)),
    ("eval-exec", re.compile(r"\beval\s+[\"'$]", re.IGNORECASE)),
    ("interpreter-delete", re.compile(
        r"\b(?:python3?|node|ruby|perl)\b[^\n]*\s-[ce]\b[^\n]*"
        r"(?:rmtree|os\.remove|os\.unlink|unlinkSync|rmSync|File\.delete)",
        re.IGNORECASE)),
]

# Split on shell command separators — but NOT a bare pipe, so pipelines stay
# intact (handled by WHOLE_RULES) and `find ... | xargs rm` is not severed.
SHELL_SEP = re.compile(r"&&|\|\||;|\n")

# Allowlist (default-deny) for the unattended SDK generator.
ALLOWED_TOOLS: frozenset[str] = frozenset({
    "Bash", "bash", "BashOutput",
    "Read", "Edit", "Write", "MultiEdit",
    "Glob", "Grep", "LS",
    "NotebookEdit", "NotebookRead", "TodoWrite",
})

# MCP tools whose name alone implies an irreversible/production effect.
MCP_DESTRUCTIVE_NAME = re.compile(
    r"mcp__.*(?:apply_migration|delete_branch|delete_project|pause_project|"
    r"reset_branch|deploy_to_vercel|delete_event|delete_|merge_branch)", re.IGNORECASE)

# MCP tools that only read — safe to allow under the default-deny posture.
MCP_READONLY_NAME = re.compile(
    r"mcp__.*(?:list_|get_|search|read_|fetch|check_|status|describe|"
    r"download_|find_|suggest|complete_authentication|authenticate)", re.IGNORECASE)


# ===========================================================================
# Canonical classifier — the single source of truth for the autonomy tier.
# ===========================================================================
def classify(tool_name: str, tool_input: Optional[dict[str, Any]]) -> int:
    """Return the autonomy tier (0-3) for a pending tool call.

    Decision rule (autonomy-ladder): rate by reversibility x domain breadth; the
    HIGHER wins; when genuinely unsure between two tiers, take the higher.

    This is the shared tier both gates agree on (RA-6882). Each gate then applies
    its own *disposition* to that tier: the SDK loop denies by default-deny
    allowlist (and additionally refuses SDK-subset local-destructive commands);
    the CLI hook denies only tier == L3 and passes L0-L2 to the human.
    """
    tool_input = tool_input or {}
    name = tool_name or ""

    # Tool-name L3 (MCP prod deploys / migrations / destructive verbs) — first.
    if L3_TOOL_RE.search(name) or L3_VERB_RE.search(name):
        return TIER_IRREVERSIBLE

    if name == "Bash":
        cmd = str(tool_input.get("command", ""))
        if L3_BASH_RE.search(cmd):
            return TIER_IRREVERSIBLE
        if READ_ONLY_BASH.search(cmd):
            return TIER_READ
        if L2_BASH.search(cmd):
            return TIER_OUTWARD
        return TIER_LOCAL

    if name in READ_ONLY_TOOLS:
        return TIER_READ

    if name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return TIER_LOCAL

    # Unknown tools default to L1 (local/reversible) — do NOT over-block; the
    # destructive-verb / tool-name guards above already lift the dangerous ones.
    return TIER_LOCAL


__all__ = [
    "TIER_READ", "TIER_LOCAL", "TIER_OUTWARD", "TIER_IRREVERSIBLE",
    "READ_ONLY_TOOLS", "READ_ONLY_BASH", "L2_BASH", "L3_BASH_RE",
    "L3_TOOL_RE", "L3_VERB_RE",
    "SEGMENT_RULES", "WHOLE_RULES", "SHELL_SEP",
    "ALLOWED_TOOLS", "MCP_DESTRUCTIVE_NAME", "MCP_READONLY_NAME",
    "classify",
]
