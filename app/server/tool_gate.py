"""SDK tool admission and workspace file boundaries.

The unattended generator permits a small tool set, resolves file targets inside
its workspace, and rejects credential/control paths. Bash uses Main's shared
rules, quote-aware and legacy segmentation, and L3 classification backstop.

Command inspection is defense in depth: arbitrary interpreter payloads cannot
be secured by regex. The SDK execution boundary must also enforce OS isolation;
this gate never substitutes for it. Path resolution consults the filesystem,
while escalation and SDK imports remain in the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    TIER_IRREVERSIBLE as _TIER_IRREVERSIBLE,
    WHOLE_RULES as _WHOLE_RULES,
    classify as _classify,
)

# RA-7412's quote-aware segmentation. Kept next door rather than here because it
# answers a mechanical question (which pieces of a command should be matched)
# with no notion of permission — and because its post-mortem is longer than the
# policy it serves. See that module before changing how a command is split.
from app.server.bash_segments import requoted_segments, segment_denial


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


# These tools have explicit single-file targets, so the hook can validate their
# resolved path. Search runs through sandboxed Bash; broad SDK searches otherwise
# read files before can_use_tool is consulted and can expose ignored credentials.
WORKSPACE_TOOLS = frozenset({"Bash", "Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "TodoWrite"})
_PRIVATE_PARTS = {".git", ".claude", ".ssh", ".aws", ".session-secret", ".password-hash"}


def _workspace_decision(tool_name: str, tool_input: dict, workspace: str) -> ToolGateDecision:
    def reject(reason: str) -> ToolGateDecision:
        return ToolGateDecision(False, "irreversible", reason, "workspace-boundary")

    if tool_name not in WORKSPACE_TOOLS:
        return reject("Tool is not permitted in the confined workspace; use sandboxed Bash for searches.")
    if tool_name == "Bash":
        if tool_input.get("dangerouslyDisableSandbox"):
            return reject("Unsandboxed command execution is not permitted.")
        return _ALLOW
    if tool_name == "TodoWrite":
        return _ALLOW
    raw = tool_input.get("notebook_path" if tool_name == "NotebookEdit" else "file_path")
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return reject("A valid workspace file path is required.")
    try:
        root = Path(workspace).resolve(strict=True)
        target = (root / raw).resolve()
        relative = target.relative_to(root)
    except (ValueError, OSError, RuntimeError):
        return reject("File access outside the workspace is not permitted.")
    if any(p.lower() in _PRIVATE_PARTS or p.lower().startswith(".env") for p in relative.parts):
        return reject("Credential and execution-control files are not available to the agent.")
    if target.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return reject("Credential files are not available to the agent.")
    return _ALLOW


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


# Enforce shared L3 classification after both quote-aware and legacy passes.
def _inspect_bash(tool_name: str, tool_input: dict) -> ToolGateDecision:
    """Per-segment + whole-command denylist over a Bash command. Allow if clean."""
    cmd = _command_text(tool_name, tool_input)
    if not cmd:
        return _ALLOW

    for label, pat in _WHOLE_RULES:
        if pat.search(cmd):
            return _deny(label)

    # RA-7412: the added quote-aware pass. Runs first only because it is cheap;
    # both passes run and either one denies, so order carries no meaning.
    requoted, git_rm_exempt = requoted_segments(cmd)
    for seg in requoted:
        label = segment_denial(seg, git_rm_exempt)
        if label:
            return _deny(label)

    # The original quote-blind pass, unchanged in behaviour and deliberately kept:
    # for the forward-scanning rules it is the STRONGER reading, and dropping it
    # would trade one leak for another. RA-7386's normalisation and the `git rm`
    # exemption live in `bash_segments.segment_denial`, shared by both passes so
    # they cannot drift apart.
    for seg in (s.strip() for s in _SHELL_SEP.split(cmd)):
        label = segment_denial(seg)
        if label:
            return _deny(label)

    # RA-7413 — the L3 backstop; see the note above `_inspect_bash`. Last, not
    # first, so every denial the rules above make keeps its own precise label.
    if _classify("Bash", {"command": cmd}) == _TIER_IRREVERSIBLE:
        return _deny("l3-irreversible")

    return _ALLOW


def decide(tool_name: str, tool_input: dict | None, *, workspace: str | None = None) -> ToolGateDecision:
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
    if workspace is not None:
        boundary = _workspace_decision(tool_name, tool_input, workspace)
        if not boundary.allow:
            return boundary

    if tool_name.startswith("mcp__"):
        return _mcp_decision(tool_name, tool_input)

    if tool_name not in ALLOWED_TOOLS:
        return _deny("tool-not-allowlisted")

    if tool_name in _BASH_TOOLS:
        return _inspect_bash(tool_name, tool_input)

    return _ALLOW


__all__ = ["ToolGateDecision", "decide"]
