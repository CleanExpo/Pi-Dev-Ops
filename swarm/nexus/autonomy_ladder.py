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

# RA-7387: the L3 Bash rule table lives next door so it can grow — this file
# sits on a size-gate baseline. Re-exported so every existing importer of
# `autonomy_ladder.L3_BASH_RE` keeps working unchanged.
#
# THE FALLBACK IS LOAD-BEARING, not defensive clutter. This module is also
# loaded BY PATH, with no package context — `tests/test_autonomy_ladder_l3_
# segments.py` does exactly that and says why: "`swarm.nexus` need not be
# importable". A relative import raises ImportError under that loader, so the
# split would have silently traded one gate bypass for an unloadable gate. The
# live PreToolUse hook imports as a package (`.claude/hooks/autonomy_gate_hook`
# puts the repo root on sys.path first), so it takes the fast path above; the
# fallback exists for every other loader.
try:
    from .autonomy_rules import (  # noqa: F401
        GIT_GLOBAL_OPT, L3_BASH_EXCLUDING_PUSH_TARGET_RE, L3_BASH_RE,
        SEGMENT_RULES, WHOLE_RULES, _L3_BASH, push_targets_are_all_unprotected,
        strip_git_global_opts,
    )
except ImportError:  # pragma: no cover - exercised by the by-path test loader
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "autonomy_rules", _Path(__file__).with_name("autonomy_rules.py"))
    _rules = _ilu.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_rules)
    L3_BASH_RE, _L3_BASH = _rules.L3_BASH_RE, _rules._L3_BASH
    SEGMENT_RULES, WHOLE_RULES = _rules.SEGMENT_RULES, _rules.WHOLE_RULES
    L3_BASH_EXCLUDING_PUSH_TARGET_RE = _rules.L3_BASH_EXCLUDING_PUSH_TARGET_RE
    push_targets_are_all_unprotected = _rules.push_targets_are_all_unprotected
    GIT_GLOBAL_OPT = _rules.GIT_GLOBAL_OPT
    strip_git_global_opts = _rules.strip_git_global_opts

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
#
# The push rules keep a WHOLE-LINE `[^\n]*` gap, so any later protected token
# satisfies them. Three attempts to narrow that gap with a smarter REGEX all
# opened real bypasses (RA-7382) and are not to be retried here. RA-7383 closed
# it a different way — an authoritative whole-line match that a bounded,
# fail-closed parser may only ever SUBTRACT from. That parser, the three
# post-mortems and the adversarial round that attacked it live in
# `swarm/nexus/push_targets.py` and
# `tests/test_autonomy_ladder_l3_segments.py`. Read both before touching this.

# --- L3: strategic / irreversible — non-Bash tool-name signatures ----------
# MCP + built-in tool names that are inherently L3.
L3_TOOL_RE = re.compile(
    r"(deploy_to_vercel|apply_migration|deploy_edge_function|create_project"
    r"|pause_project|restore_project|delete_branch|merge_branch|db_push)",
    re.IGNORECASE,
)
# Destructive/strategic verbs in an otherwise-unknown tool name -> higher tier.
L3_VERB_RE = re.compile(r"(rotate|charge|payout|transfer|drop_)", re.IGNORECASE)
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
        return _classify_bash(str(tool_input.get("command", "")))

    if name in READ_ONLY_TOOLS:
        return TIER_READ

    if name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return TIER_LOCAL

    # Unknown tools default to L1 (local/reversible) — do NOT over-block; the
    # destructive-verb / tool-name guards above already lift the dangerous ones.
    return TIER_LOCAL


def _bash_is_l3(cmd: str, norm: str) -> tuple[bool, bool]:
    """`(is_l3, push_was_subtracted)` for one Bash command.

    Split from `_classify_bash` under the 40-line rule, and it earns the split:
    this is the only place a tier can be RAISED, and the caller is the only place
    one can be lowered. Keeping those apart is what makes "the narrowing can only
    touch a push verdict" checkable by reading rather than by trusting.
    """
    # RA-7383: an L3 signature that is NOT one of the two target-based push rules
    # is decided here and never reconsidered.
    if (L3_BASH_EXCLUDING_PUSH_TARGET_RE.search(cmd)
            or L3_BASH_EXCLUDING_PUSH_TARGET_RE.search(norm)):
        return True, False
    if L3_BASH_RE.search(cmd) or L3_BASH_RE.search(norm):
        # Only the whole-line push gap matched. Stay L3 unless BOTH spellings are
        # provably targeting unprotected refs. `and`, not `or`: the normalised
        # form exists so a global-option spelling cannot duck the rule, so a
        # clearance holding for only one of the two is no clearance. Any doubt
        # inside the helper returns False.
        if not (push_targets_are_all_unprotected(cmd)
                and push_targets_are_all_unprotected(norm)):
            return True, False
        return False, True
    return False, False


def _classify_bash(cmd: str) -> int:
    """Tier for one Bash command. Extracted from `classify` under the 40-line rule.

    Order is load-bearing: L3 first so nothing can talk a strategic action down,
    then the read-only and outward rules, each of which LOWERS the tier and so
    must never see a push the narrowing has already cleared.
    """
    # RA-7386: also test the form with git's global options stripped, so
    # `git -C . push origin main` cannot duck the L3 rules. Original OR
    # normalised, so this can only ever RAISE the tier — and deliberately
    # NOT applied to READ_ONLY_BASH, where a hit LOWERS it.
    norm = strip_git_global_opts(cmd)
    is_l3, push_subtracted = _bash_is_l3(cmd, norm)
    if is_l3:
        return TIER_IRREVERSIBLE
    # A subtracted push must not fall into the read-only branch. READ_ONLY_BASH
    # matches on the FIRST command in a chain, so `git status && git push
    # origin feature/x && echo main` would score L0 — a WRITE classified as a
    # read. That over-match is older than this change and reachable without it
    # (the same command minus `echo main` already scores L0 on main, filed as
    # RA-7410), but the narrowing routes a new class of command into it, so it
    # is floored here rather than left to be inherited.
    if READ_ONLY_BASH.search(cmd) and not push_subtracted:
        return TIER_READ
    # `or push_subtracted` for the same reason as the floor above, one tier
    # down. L2_BASH's push pattern carries the SAME whole-line lookahead —
    # `git push` not followed anywhere by a protected token — because L3 used
    # to own every command that had one. Now that L3 subtracts some of them,
    # they fall out of L2's lookahead too and would land at L1: `git push
    # origin feature/x && echo main` scoring BELOW the identical
    # `git push origin feature/x && echo hi`, which is L2. A subtracted push
    # is still a push, so it is outward by L2_BASH's own intent.
    if L2_BASH.search(cmd) or L2_BASH.search(norm) or push_subtracted:
        return TIER_OUTWARD
    return TIER_LOCAL


__all__ = [
    "TIER_READ", "TIER_LOCAL", "TIER_OUTWARD", "TIER_IRREVERSIBLE",
    "READ_ONLY_TOOLS", "READ_ONLY_BASH", "L2_BASH", "L3_BASH_RE",
    "L3_TOOL_RE", "L3_VERB_RE",
    "SEGMENT_RULES", "WHOLE_RULES", "SHELL_SEP",
    "GIT_GLOBAL_OPT", "strip_git_global_opts",
    "ALLOWED_TOOLS", "MCP_DESTRUCTIVE_NAME", "MCP_READONLY_NAME",
    "classify",
]
