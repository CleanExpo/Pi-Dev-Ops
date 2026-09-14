"""Planner admission policy: JSON-only SDK call, visible failure reasons.

Pipeline Smoke session 49e62041 (Actions 34793463387, Railway deploy
f4fd797e) showed trust #750 succeeding, then the planner hanging until
``SDK generator timed out after 120s``. ``_run_claude_via_sdk`` maps that
to ``rc=1`` with empty text; ``_phase_plan`` then reports
``planner returned exit status 1`` and blocks generate.

The planner prompt is JSON-only. The generator SDK path is not: all tools,
adaptive thinking, no turn cap. Combined with the smoke brief's
"Full feature audit first" (classified detailed → 120 s budget) Claude
explores the clone until the timeout.

Official SDK docs: ``tools=[]`` disables built-in tools. ``allowed_tools=[]``
does not — that flag is permission pre-approval and an empty list is omitted.
"""

from __future__ import annotations

PLANNER_MAX_TURNS: int = 1
PLANNER_ROLE: str = "planner"


def is_planner_phase(phase: str) -> bool:
    """True when the SDK ``phase`` role is the RA-1026 planner."""
    return (phase or "").split(".")[0] == PLANNER_ROLE


def plan_timeouts(tier: str) -> tuple[int, int]:
    """Return ``(sdk_timeout_s, wait_timeout_s)`` for the plan phase.

    detailed/advanced keep the longer window from RA-1178. The planner is
    now JSON-only, so both budgets should finish well inside this.
    """
    if (tier or "").lower() in ("detailed", "advanced"):
        return 120, 130
    return 60, 70


def planner_thinking_mode(phase: str, thinking: str, *, is_fable: bool) -> str:
    """Disable extended thinking for planner. Fable still requires adaptive."""
    if is_fable:
        return thinking
    if is_planner_phase(phase):
        return "disabled"
    return thinking


def planner_agent_option_overrides() -> dict[str, object]:
    """ClaudeAgentOptions kwargs that make the planner a single JSON turn.

    ``tools=[]`` is the documented "no built-in tools" switch
    (code.claude.com/docs/en/agent-sdk/python). ``setting_sources=[]``
    stops project ``permissions.allow`` from re-injecting Bash.
    """
    return {
        "tools": [],
        "max_turns": PLANNER_MAX_TURNS,
        "setting_sources": [],
    }


def apply_planner_agent_options(opts: dict, phase: str) -> dict:
    """Merge planner restrictions into SDK option kwargs. Other phases unchanged."""
    if is_planner_phase(phase):
        opts.update(planner_agent_option_overrides())
    return opts


def compose_agent_options(
    *,
    workspace: str,
    model: str,
    thinking_cfg: object,
    effort: object,
    betas: list,
    gate_on: bool,
    phase: str,
    can_use_tool: object = None,
) -> dict:
    """Build ClaudeAgentOptions kwargs. Planner is JSON-only (no tools).

    Generator keeps every built-in tool (RA-1172 bypassPermissions). Planner
    must not: tools + adaptive thinking is what burned 120 s then rc=1 on
    session 49e62041 (RA-7546).
    """
    opts: dict = {
        "cwd": workspace,
        "model": model,
        "thinking": thinking_cfg,
        "effort": effort,
        "betas": betas,
        "permission_mode": "default" if gate_on else "bypassPermissions",
        "can_use_tool": can_use_tool if gate_on else None,
    }
    if gate_on:
        opts["setting_sources"] = []
    return apply_planner_agent_options(opts, phase)


def instantiate_agent_options(option_cls: type, opts: dict):
    """Drop kwargs the installed SDK dataclass does not accept (e.g. ``tools``)."""
    from dataclasses import fields, is_dataclass  # noqa: PLC0415

    if is_dataclass(option_cls):
        valid = {item.name for item in fields(option_cls)}
        opts = {key: value for key, value in opts.items() if key in valid}
    return option_cls(**opts)


def sdk_failure_detail(rc: int, text: str) -> str:
    """Human-readable plan-block reason, including swallowed SDK errors."""
    extra = (text or "").strip()
    if rc != 0:
        if extra:
            return f"planner returned exit status {rc} ({extra})"
        return f"planner returned exit status {rc}"
    return "planner returned empty output"
