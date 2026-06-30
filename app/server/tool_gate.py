"""
app/server/tool_gate.py — SDK-layer irreversible-action interceptor.

The autonomous coding loop runs each generator turn under the SDK with tool
execution enabled. The structured reversibility gate (swarm/nexus/policy.py)
only classifies pre-stamped business actions (spend, drafts); it never sees a
destructive *tool call* (rm -rf, prod deploy, DROP TABLE) issued inside a
generator turn. This module closes the obvious paths via a high-precision
denylist consulted by the SDK ``can_use_tool`` callback (see session_sdk).

HONEST SCOPE — defense-in-depth, NOT a guarantee. This is a regex denylist
evaluated against command strings authored by the very agent it polices. It
stops naive/literal destructive calls (the common accidental case). It does
NOT stop a determined agent: write-then-execute a script (Write is allowed),
arbitrary interpreter payloads, or novel obfuscation will get through. The
real guarantee is an allowlist of permitted tools (``allowed_tools``); that is
the tracked follow-up. Do not represent this gate as "irreversible actions are
now blocked" — represent it as "common destructive commands are intercepted".

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


# Per-segment rules: matched against each shell segment independently (split on
# &&, ||, ;, newline) so flags from an unrelated chained command cannot bleed
# into another's match. Each is narrow — operations that destroy state with no
# git/undo path, or that push to a production/external system.
_SEGMENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    # Recursive+forced delete (rm -rf, rm -fr, rm -r -f, rm --recursive --force)
    ("rm-rf", re.compile(
        r"\brm\b(?=(?:[^\n]*\s-{1,2}[a-z-]*r))(?=(?:[^\n]*\s-{1,2}[a-z-]*f))",
        re.IGNORECASE)),
    # find-based bulk delete
    ("find-delete", re.compile(r"\bfind\b[^\n]*\s-delete\b", re.IGNORECASE)),
    ("find-exec-rm", re.compile(r"\bfind\b[^\n]*-exec\s+rm\b", re.IGNORECASE)),
    # Force push to a remote (--force, --force-with-lease, -f, or +refspec)
    ("git-force-push", re.compile(
        r"\bgit\s+push\b[^\n]*\s(?:--force\b|--force-with-lease\b|-[a-z]*f\b|\+[\w./-]+)",
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

# Whole-command rules: inherently cross-segment (a pipe IS the payload), so they
# must see the full command, not a split segment.
_WHOLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("pipe-to-shell", re.compile(
        r"(?:curl|wget|fetch|base64)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE)),
    ("eval-exec", re.compile(r"\beval\s+[\"'$]", re.IGNORECASE)),
    # Interpreter one-liners that delete from the filesystem. Whole-command:
    # the payload after -c/-e legitimately contains `;`, so it must not be split.
    ("interpreter-delete", re.compile(
        r"\b(?:python3?|node|ruby|perl)\b[^\n]*\s-[ce]\b[^\n]*"
        r"(?:rmtree|os\.remove|os\.unlink|unlinkSync|rmSync|File\.delete)",
        re.IGNORECASE)),
]

# Split on shell command separators — but NOT a bare pipe, so pipelines stay
# intact (handled by _WHOLE_RULES) and `find ... | xargs rm` is not severed.
_SHELL_SEP = re.compile(r"&&|\|\||;|\n")

_BASH_TOOLS = {"Bash", "bash", "BashOutput"}

# MCP tools whose name alone implies an irreversible/production effect.
_MCP_DESTRUCTIVE_NAME = re.compile(
    r"mcp__.*(?:apply_migration|delete_branch|delete_project|pause_project|"
    r"reset_branch|deploy_to_vercel|delete_event)", re.IGNORECASE)


def _command_text(tool_name: str, tool_input: dict) -> str:
    """Extract the shell command from a Bash-family tool call; else ''."""
    if tool_name not in _BASH_TOOLS:
        return ""
    cmd = tool_input.get("command", "")
    return cmd if isinstance(cmd, str) else ""


def _deny(label: str) -> ToolGateDecision:
    return ToolGateDecision(
        allow=False, reversibility="irreversible", label=label,
        reason=(
            f"Blocked irreversible operation ({label}). Per the locked autonomy "
            f"boundary, destructive/irreversible actions require founder approval "
            f"and are not auto-run."
        ),
    )


_ALLOW = ToolGateDecision(True, "reversible", "", "")


def _mcp_decision(tool_name: str, tool_input: dict) -> ToolGateDecision:
    """Inspect MCP tool calls: destructive by name, or execute_sql by payload."""
    if _MCP_DESTRUCTIVE_NAME.search(tool_name):
        return _deny("mcp-destructive")
    if "execute_sql" in tool_name.lower():
        sql = tool_input.get("query") or tool_input.get("sql") or ""
        if isinstance(sql, str):
            for label, pat in _SEGMENT_RULES:
                if label.startswith("sql-") and pat.search(sql):
                    return _deny(label)
    return _ALLOW


def decide(tool_name: str, tool_input: dict | None) -> ToolGateDecision:
    """Return an allow/deny decision for a single tool call.

    Bash-family commands are inspected per shell segment; MCP tools by name and
    (for execute_sql) by payload. All other tools (Read, Edit, Write, Grep, …)
    are allowed — file edits are git-reversible. Recognised irreversible calls
    are denied with a founder-facing reason. Errs toward ALLOW on anything
    unrecognised (see module scope note).
    """
    tool_input = tool_input or {}

    if tool_name.startswith("mcp__"):
        return _mcp_decision(tool_name, tool_input)

    cmd = _command_text(tool_name, tool_input)
    if not cmd:
        return _ALLOW

    for label, pat in _WHOLE_RULES:
        if pat.search(cmd):
            return _deny(label)

    for seg in (s.strip() for s in _SHELL_SEP.split(cmd)):
        if not seg or re.match(r"git\s+rm\b", seg, re.IGNORECASE):
            continue  # `git rm` is tracked/recoverable — not the rm-rf rule
        for label, pat in _SEGMENT_RULES:
            if pat.search(seg):
                return _deny(label)

    return _ALLOW


__all__ = ["ToolGateDecision", "decide"]
