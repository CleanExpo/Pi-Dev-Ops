"""SDK query options. Planner is text-only so it cannot tool-loop a clone.

RA-7546 quiet-tip Pipeline Smoke (run 34790637141): planner called
``_run_claude_via_sdk(..., phase="planner")`` with the generator default
(every Claude Code tool, ``bypassPermissions``). Clone+prep finished in 4 s;
the planner then burned the 120 s detailed-tier budget exploring Pi-Dev-Ops.
The SDK timed out (``SDK generator timed out after 120s``) and returned
rc=1, which ``_phase_plan`` recorded as ``planner returned exit status 1``.
Generate never started.

The planner prompt is JSON-only. Tools are counterproductive there.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

_log = logging.getLogger("pi-ceo.sdk_call_options")

TEXT_ONLY_ROLES = frozenset({"planner"})


def role_of(phase: str) -> str:
    """Map a dotted phase label to the role ``model_policy`` uses."""
    return (phase or "").split(".")[0] or "generator"


def is_text_only_phase(phase: str) -> bool:
    """True when the phase must emit text and must not invoke tools."""
    return role_of(phase) in TEXT_ONLY_ROLES


def usage_output_tokens(usage: Any) -> Optional[int]:
    """Best-effort billed output_tokens from an SDK usage payload."""
    if usage is None:
        return None
    try:
        if isinstance(usage, dict):
            return usage.get("output_tokens")
        return getattr(usage, "output_tokens", None)
    except Exception:
        return None


def sdk_query_kwargs(
    *,
    workspace: str,
    model: str,
    thinking_cfg: object,
    effort: object,
    prompt_cache: bool,
    tool_gate_on: bool,
    can_use_tool: object | None,
    phase: str,
) -> dict[str, Any]:
    """Build ``ClaudeAgentOptions`` kwargs for one SDK query.

    Generator keeps the proven full-tool ``bypassPermissions`` path (RA-1172).
    Planner is pinned to zero tools and one turn so a clone cannot eat the
    plan budget (RA-7546).
    """
    betas: list[str] = ["prompt-caching-2024-07-31"] if prompt_cache else []
    opts: dict[str, Any] = {
        "cwd": workspace,
        "model": model,
        "thinking": thinking_cfg,
        "effort": effort,
        "betas": betas,
        "permission_mode": "default" if tool_gate_on else "bypassPermissions",
        "can_use_tool": can_use_tool if tool_gate_on else None,
    }
    if tool_gate_on:
        # Pin setting_sources so ~/.claude/settings.json cannot bypass the gate.
        opts["setting_sources"] = []
    if is_text_only_phase(phase):
        opts["allowed_tools"] = []
        opts["max_turns"] = 1
        opts["setting_sources"] = []
        _log.info("SDK text-only phase=%s (no tools, max_turns=1)", phase)
    return opts
