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

# RA-6882: the destructive/strategic signature registry and the ``ALLOWED_TOOLS``
# allowlist now live in ``swarm.nexus.autonomy_ladder`` — the single source of
# truth shared with the interactive CLI gate ``swarm/nexus/autonomy_gate.py``.
# This module keeps only its *disposition*: default-deny allowlist for the
# unattended SDK loop, with Bash inspected against the shared denylist. The
# subset it enforces (segment + whole rules, MCP-name governance) is a
# deliberately broader denylist than the CLI hook's tier==L3-only rule; that
# divergence is intentional (unattended vs human-present) and documented here.
from swarm.nexus.autonomy_ladder import (
    ALLOWED_TOOLS,
    MCP_DESTRUCTIVE_NAME as _MCP_DESTRUCTIVE_NAME,
    MCP_READONLY_NAME as _MCP_READONLY_NAME,
    SEGMENT_RULES as _SEGMENT_RULES,
    SHELL_SEP as _SHELL_SEP,
    WHOLE_RULES as _WHOLE_RULES,
)


@dataclass(frozen=True)
class ToolGateDecision:
    allow: bool
    reversibility: str  # "reversible" | "irreversible"
    reason: str
    label: str = ""     # short tag of the matched rule, for audit/dedup


_BASH_TOOLS = {"Bash", "bash", "BashOutput"}


def _command_text(tool_name: str, tool_input: dict) -> str:
    """Extract the shell command from a Bash-family tool call; else ''."""
    if tool_name not in _BASH_TOOLS:
        return ""
    cmd = tool_input.get("command", "")
    return cmd if isinstance(cmd, str) else ""


_ALLOWLIST_LABELS = {"tool-not-allowlisted", "mcp-write-not-allowlisted"}


def _deny(label: str) -> ToolGateDecision:
    if label in _ALLOWLIST_LABELS:
        reason = (
            f"Tool not permitted for the autonomous generator ({label}). Only "
            f"code-editing, search, and inspected-Bash tools are allowed; "
            f"writes to external systems go through the structured approval gate."
        )
    else:
        reason = (
            f"Blocked irreversible operation ({label}). Per the locked autonomy "
            f"boundary, destructive/irreversible actions require founder approval "
            f"and are not auto-run."
        )
    return ToolGateDecision(
        allow=False, reversibility="irreversible", label=label, reason=reason,
    )


_ALLOW = ToolGateDecision(True, "reversible", "", "")


def _mcp_decision(tool_name: str, tool_input: dict) -> ToolGateDecision:
    """Govern MCP tool calls under default-deny.

    Destructive-by-name → deny; execute_sql → inspect payload; read-only name →
    allow; anything else (an MCP write) → deny. The autonomous generator writes
    code + runs tests; it has no need to mutate Linear/Supabase/Vercel mid-run.
    """
    if _MCP_DESTRUCTIVE_NAME.search(tool_name):
        return _deny("mcp-destructive")
    if "execute_sql" in tool_name.lower():
        sql = tool_input.get("query") or tool_input.get("sql") or ""
        if isinstance(sql, str):
            for label, pat in _SEGMENT_RULES:
                if label.startswith("sql-") and pat.search(sql):
                    return _deny(label)
        return _ALLOW
    if _MCP_READONLY_NAME.search(tool_name):
        return _ALLOW
    return _deny("mcp-write-not-allowlisted")


def _inspect_bash(tool_name: str, tool_input: dict) -> ToolGateDecision:
    """Per-segment + whole-command denylist over a Bash command. Allow if clean."""
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


def decide(tool_name: str, tool_input: dict | None) -> ToolGateDecision:
    """Allowlist gate (default-deny) for a single tool call.

    * MCP tools → governed by _mcp_decision (read-only allowed, writes denied).
    * Built-in tools NOT on ALLOWED_TOOLS → denied (e.g. Task, which would let a
      subagent's tool calls bypass this gate entirely).
    * Bash → permitted but the command is inspected for destructive operations.
    * Other allowlisted tools (Read, Edit, Write, Grep, …) → allowed; file edits
      are git-reversible.

    Honest limit (see module scope note): Bash must stay permitted for a coding
    agent, so write-a-script-then-execute-it and arbitrary interpreter payloads
    are not fully closed. This bounds the tool surface; it is not a sandbox.
    """
    tool_input = tool_input or {}

    if tool_name.startswith("mcp__"):
        return _mcp_decision(tool_name, tool_input)

    if tool_name not in ALLOWED_TOOLS:
        return _deny("tool-not-allowlisted")

    if tool_name in _BASH_TOOLS:
        return _inspect_bash(tool_name, tool_input)

    return _ALLOW


__all__ = ["ToolGateDecision", "decide"]
