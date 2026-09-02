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
    strip_git_global_opts as _strip_git_global_opts,
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


# RA-7412 — closing the quote-blind split, without weakening what already works.
#
# THE LEAK. `_inspect_bash` splits on `_SHELL_SEP` before testing `_SEGMENT_RULES`.
# A `;` inside a quoted ARGUMENT is data, not a command boundary, but the split
# cannot tell, so it severs the signature and neither half matches. Two commands
# reached the unattended loop ALLOWED:
#
#     vercel -e CSP="default-src 'self'; script-src 'self'" --prod   -> prod deploy
#     git -c note="a;b" reset --hard                                 -> destroys work
#
# Both are denied correctly once the quoted span is removed, which is what proved
# it was the split and not the rules. RA-7382 measured 59-75 leaks of this exact
# shape against the INTERACTIVE gate and rejected segmentation for it. This file
# kept it — and here there is no human to catch a miss.
#
# WHY NOT SIMPLY TEST THE WHOLE COMMAND TOO. Tried first; the existing suite
# rejected it, and was right to. Several rules scan forward with `[^\n]*`, so over
# an uncut chain they collect tokens from unrelated later commands:
#
#     rm notes.txt && tar -rvf archive.tar src   -> `rm` + a LATER `-rvf` = rm-rf
#
# Segmentation is not merely weaker than whole-command matching; for those rules
# it is what makes them correct. The same is true in the other direction for
# `sql-delete-no-where`, whose `(?![\s\S]*\bWHERE\b)` lookahead is suppressed by a
# WHERE in an unrelated later statement. Neither reading dominates, so this ADDS a
# pass rather than replacing one.
#
# THE ADDED PASS: split a quote-MASKED copy, then run the same rules on it. The
# masking only has to be good enough to add a denial — the original passes are
# untouched, so a masking mistake can never REMOVE protection. That is the same
# inversion RA-7383 used, and it is what makes masking safe here when RA-7382
# found it unsafe there: that design masked in order to NARROW a match.
_QUOTE_CHARS = frozenset("\"'")
# Escapes, backticks and `$(`/`${` defeat a simple masker (RA-7382 measured it).
# Their presence does not disable the pass — that would make the bypass one `$`
# away — it falls back to the strictest reading instead: the whole command as a
# single segment.
_MASK_UNSAFE = frozenset("\\`$")
_QUOTED_SPAN = re.compile(r"\"[^\"]*\"|'[^']*'")

# THREE THINGS `_requoted_segments` GETS RIGHT, each of which it got wrong first
# and each caught by measurement rather than by reading the code:
#
# 1. The trigger covers everything that can HIDE a separator, not just quotes.
#    Testing for `"`/`'` alone left ``vercel --meta note=`echo a;b` --prod``
#    leaking — it carries no quote character, so the pass was skipped entirely and
#    the ordinary split severed the signature at the backticked `;`. A trigger
#    narrower than the set of hiding places is a bypass one backtick wide.
#
# 2. An unclosed quote invalidates the mask, so it takes the strict path. There is
#    no complete span to blank in `vercel -e "a;b --prod`, so masking is a no-op
#    and the split severs exactly as before. The leftover-quote test runs on the
#    MASKED text on purpose: an apostrophe inside a double-quoted span
#    (`echo "don't"`) reads as unbalanced before masking and balanced after, so
#    counting up front would send ordinary commands down the strict path.
#
# 3. The `git rm` exemption does NOT travel with the strict path. It is a claim
#    about ONE command — `git rm -rf x` is recoverable — and `re.match` anchors it
#    at the start, so on an uncut chain it exempted everything after the first
#    command too:
#        git rm x && vercel -e "a;$X" --prod   -> allowed
#        ls        && vercel -e "a;$X" --prod  -> denied   (the control)
#    Prefixing a chain with `git rm x &&` must not launder the rest of it.


def _requoted_segments(cmd: str) -> tuple[list[str], bool]:
    """Segments for the ADDED pass, and whether the `git rm` exemption applies.

    No segments means the ordinary split is already correct. The flag is False
    when the single "segment" is the whole uncut command. See the notes above the
    constants for why each branch is shaped the way it is.
    """
    has_quote = any(ch in _QUOTE_CHARS for ch in cmd)
    has_unsafe = any(ch in _MASK_UNSAFE for ch in cmd)
    if not has_quote and not has_unsafe:
        return [], True
    if has_unsafe:
        return [cmd], False
    # Blank each quoted span so separators inside it stop being boundaries. A
    # space, not a placeholder token, so the masked text cannot invent a match.
    masked = _QUOTED_SPAN.sub(lambda m: " " * len(m.group(0)), cmd)
    # A quote left over means a span never closed, so the mask is not trustworthy
    # — `vercel -e "a;b --prod` has no complete span to blank and would split at
    # the quoted `;` exactly as before. Counting quotes up front would be worse
    # than this: an apostrophe inside a double-quoted span (`echo "don't"`) reads
    # as unbalanced before masking and as balanced after, so the check has to run
    # on the masked text or it sends ordinary commands down the strict path.
    if any(ch in _QUOTE_CHARS for ch in masked):
        return [cmd], False
    return [s.strip() for s in _SHELL_SEP.split(masked)], True


def _segment_denial(seg: str, git_rm_exempt: bool = True) -> str | None:
    """The label of the first `_SEGMENT_RULES` hit on a segment, or None.

    Carries the RA-7386 contract with it: the original AND the global-option
    normalised form are both tested, and the `git rm` exemption is applied PER
    FORM, so `git -C . rm -rf .` stays denied while `git rm -rf cached` does not.
    """
    for cand in (seg, _strip_git_global_opts(seg)):
        if not cand:
            continue
        if git_rm_exempt and re.match(r"git\s+rm\b", cand, re.IGNORECASE):
            continue  # `git rm` is tracked/recoverable — not the rm-rf rule
        for label, pat in _SEGMENT_RULES:
            if pat.search(cand):
                return label
    return None


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
    requoted, git_rm_exempt = _requoted_segments(cmd)
    for seg in requoted:
        label = _segment_denial(seg, git_rm_exempt)
        if label:
            return _deny(label)

    # The original quote-blind pass, unchanged in behaviour and deliberately kept:
    # for the forward-scanning rules it is the STRONGER reading, and dropping it
    # would trade one leak for another. RA-7386's normalisation and the `git rm`
    # exemption now live in `_segment_denial`, shared by both passes so they
    # cannot drift apart.
    for seg in (s.strip() for s in _SHELL_SEP.split(cmd)):
        label = _segment_denial(seg)
        if label:
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
