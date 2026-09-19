"""
session_sdk.py — Claude Agent SDK invocation and SDK metrics helpers.

Extracted from sessions.py (RA-890). Contains:
  - _SDK_METRICS_DIR       — path to agent-sdk-metrics JSONL directory
  - _write_sdk_metric()    — append one invocation row to today's JSONL
  - _emit_sdk_canary_metric() — canary row (used by tests / health checks)
  - _run_claude_via_sdk()  — run Claude via claude_agent_sdk, return (rc, text, cost)

Execution admission and per-attempt streaming live in focused SDK helper modules.
All other session modules that call _run_claude_via_sdk should import from here.

Public API (re-exported by sessions.py for backward compatibility):
    _SDK_METRICS_DIR
    _write_sdk_metric()
    _emit_sdk_canary_metric()
    _run_claude_via_sdk()
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Optional

from . import config
from . import model_registry
from . import tool_gate
from . import sdk_execution_boundary as _boundary
from .sdk_execution_boundary import (  # noqa: F401 - compatibility and readiness exports
    ExecutionBoundaryError, _child_environment, _cli_identity, _execution_cli,
    _require_supported_cli, generation_readiness, shutil, subprocess, sys,
)


def _execution_options(workspace: str) -> dict:
    return _boundary._execution_options(
        workspace, cli_resolver=_execution_cli, version_check=_require_supported_cli,
        gate_factory=_make_can_use_tool, pretool_factory=_make_pre_tool_use,
    )

_log = logging.getLogger("pi-ceo.session_sdk")


# ── Tool gate (RA — SDK-layer irreversible-action interceptor) ──────────────────

async def _tool_gate_stream(prompt: str, session_id: str):
    """Wrap a string prompt as the single-message async stream can_use_tool needs.

    can_use_tool requires streaming mode (AsyncIterable prompt), not a str —
    see claude_agent_sdk client.py. This yields exactly one user message.
    """
    yield {
        "type": "user",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
        "session_id": session_id or "tao",
    }


def _escalate_blocked_tool(label: str, tool_name: str, reason: str) -> None:
    """Best-effort, edge-triggered Telegram escalation for a blocked tool call.

    Lazy import of swarm.telegram_alerts so app.server stays decoupled from the
    swarm package; any failure is swallowed — escalation must never break the
    loop. dedup_key keeps a persistent block from re-paging every turn.
    """
    try:
        from swarm.telegram_alerts import send  # noqa: PLC0415
        send(
            f"⛔ Tool gate blocked an irreversible action.\n\nTool: {tool_name}\n{reason}",
            severity="critical",
            bot_name="ToolGate",
            dedup_key=f"toolgate:{label}",
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("tool gate escalation failed (label=%s): %s", label, exc)


def _make_can_use_tool(workspace: str | None = None):
    """Build the SDK can_use_tool callback backed by tool_gate.decide.

    Returns PermissionResultAllow for reversible/unrecognised calls and
    PermissionResultDeny (with a founder-facing message) for recognised
    irreversible ones. Imports the SDK permission types lazily so this module
    stays importable when claude_agent_sdk is absent.
    """
    from claude_agent_sdk.types import (  # noqa: PLC0415
        PermissionResultAllow,
        PermissionResultDeny,
    )

    async def _can_use_tool(tool_name: str, tool_input: dict, context):  # noqa: ANN001
        decision = tool_gate.decide(tool_name, tool_input, workspace=workspace)
        if decision.allow:
            return PermissionResultAllow(updated_input=tool_input)
        _log.warning("tool gate DENY (%s): %s", decision.label, tool_name)
        _escalate_blocked_tool(decision.label, tool_name, decision.reason)
        return PermissionResultDeny(message=decision.reason, interrupt=False)

    return _can_use_tool


def _make_pre_tool_use(workspace: str):
    """Check every tool, including reads the CLI may otherwise auto-approve."""
    async def check(data, tool_use_id, context):
        decision = tool_gate.decide(data.get("tool_name", ""), data.get("tool_input"), workspace=workspace)
        if decision.allow:
            return {}
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason,
        }}
    return check


_SDK_METRICS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "agent-sdk-metrics"
)


# ── Metrics helpers ────────────────────────────────────────────────────────────

def _write_sdk_metric(
    *,
    session_id: str, phase: str, model: str,
    success: bool, latency_s: float, output_len: int,
    error: Optional[str] = None,
    output_tokens: Optional[int] = None,
    stop_reason: Optional[str] = None,
    requested_model: Optional[str] = None,
    actual_model: Optional[str] = None,
    observed_models: Optional[list[str]] = None,
    model_verified: bool = False,
    cost_usd: Optional[float] = None,
    cost_source: str = "unknown",
    cost_verified: bool = False,
) -> None:
    """Append best-effort invocation evidence; metric failures never stop work."""
    try:
        os.makedirs(_SDK_METRICS_DIR, exist_ok=True)
        today = datetime.date.today().isoformat()
        path = os.path.join(_SDK_METRICS_DIR, f"{today}.jsonl")
        row = json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id, "phase": phase, "model": model,
            "requested_model": requested_model or model,
            "actual_model": actual_model,
            "observed_models": observed_models or [],
            "model_verified": model_verified,
            "cost_usd": cost_usd,
            "cost_source": cost_source, "cost_verified": cost_verified,
            "sdk_enabled": True, "success": success,
            "latency_s": round(latency_s, 3),
            "output_len": output_len,
            "output_tokens": output_tokens, "stop_reason": stop_reason, "error": error,
        })
        with open(path, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except Exception:
        pass  # metrics must never break the pipeline


def _emit_sdk_canary_metric(session_id: str, success: bool) -> None:
    """Append canary metric line to .harness/agent-sdk-metrics/YYYY-MM-DD.jsonl."""
    try:
        metrics_dir = Path(config.DATA_DIR).parent.parent / ".harness" / "agent-sdk-metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        entry = json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": session_id,
            "canary": True,
            "success": success,
        })
        with open(metrics_dir / f"{date_str}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except Exception:
        pass


# ── Core SDK runner ────────────────────────────────────────────────────────────

def _usage_output_tokens(usage) -> Optional[int]:  # noqa: ANN001
    """Best-effort extract billed output_tokens from an SDK usage payload.

    The agent SDK usage may be a dict (`{"output_tokens": N}`) or an object with
    an `.output_tokens` attribute. Returns None when unavailable — amplification
    logging is best-effort and must never raise.
    """
    if usage is None:
        return None
    try:
        if isinstance(usage, dict):
            return usage.get("output_tokens")
        return getattr(usage, "output_tokens", None)
    except Exception:
        return None



async def _run_claude_via_sdk(
    prompt: str, model: str, workspace: str, timeout: int = 300,
    session_id: str = "", phase: str = "", thinking: str = "adaptive",
) -> tuple[int, str, float | None]:
    """Run an isolated subscription attempt; unknown spend stays unknown."""
    from .model_policy import assert_model_allowed, effort_for_role
    from .provider_policy import ProviderPolicyError
    from .sdk_attempt import SDKAttempt
    role = (phase or "").split(".")[0] or "generator"
    if role in config.FABLE_ALLOWED_ROLES:
        model = model_registry.ANTHROPIC_FABLE
    assert_model_allowed(role, model)
    try:
        execution = _execution_options(workspace)
        identity = _cli_identity(execution["cli_path"])
    except (ProviderPolicyError, ExecutionBoundaryError) as exc:
        reason = str(exc)
        _write_sdk_metric(session_id=session_id, phase=phase, model=model, success=False,
                          latency_s=0.0, output_len=0, error=reason)
        return 1, reason, None
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("claude_agent_sdk not installed - set USE_AGENT_SDK=0 or install it") from exc
    kwargs = dict(prompt=prompt, workspace=workspace, timeout=timeout, session_id=session_id,
                  phase=phase, thinking=thinking, effort=effort_for_role(role),
                  execution_options=execution, cli_identity=identity, metric=_write_sdk_metric,
                  stream=_tool_gate_stream)
    rc, text, cost, stop, tokens, error = await SDKAttempt(model=model, **kwargs).run()
    if (model == model_registry.ANTHROPIC_FABLE and rc != 0
            and not str(error).startswith(("subscription_only:", "execution_blocked:"))):
        first_cost = cost
        rc, text, cost, stop, tokens, error = await SDKAttempt(model=config.MODEL_ID_OPUS, **kwargs).run()
        cost = first_cost + cost if first_cost is not None and cost is not None else None
    return rc, text, cost
