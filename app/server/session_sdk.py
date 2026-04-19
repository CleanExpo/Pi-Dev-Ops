"""
session_sdk.py — Claude Agent SDK invocation and SDK metrics helpers.

Extracted from sessions.py (RA-890). Contains:
  - _SDK_METRICS_DIR       — path to agent-sdk-metrics JSONL directory
  - _write_sdk_metric()    — append one invocation row to today's JSONL
  - _emit_sdk_canary_metric() — canary row (used by tests / health checks)
  - _run_claude_via_sdk()  — run Claude via claude_agent_sdk, return (rc, text, cost)

This module depends only on standard library + config (leaf node in the import graph).
All other session modules that call _run_claude_via_sdk should import from here.

Public API (re-exported by sessions.py for backward compatibility):
    _SDK_METRICS_DIR
    _write_sdk_metric()
    _emit_sdk_canary_metric()
    _run_claude_via_sdk()
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from . import config

_log = logging.getLogger("pi-ceo.session_sdk")

# ── SDK metrics directory ──────────────────────────────────────────────────────

_SDK_METRICS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "agent-sdk-metrics"
)


# ── Metrics helpers ────────────────────────────────────────────────────────────

def _write_sdk_metric(
    *,
    session_id: str,
    phase: str,
    model: str,
    success: bool,
    latency_s: float,
    output_len: int,
    error: Optional[str] = None,
) -> None:
    """Append one SDK invocation row to today's JSONL metrics file.

    Non-blocking by design: any I/O error is silently swallowed so metrics
    failures never affect the build pipeline.
    """
    try:
        os.makedirs(_SDK_METRICS_DIR, exist_ok=True)
        today = datetime.date.today().isoformat()
        path = os.path.join(_SDK_METRICS_DIR, f"{today}.jsonl")
        row = json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "session_id": session_id,
            "phase": phase,
            "model": model,
            "sdk_enabled": True,
            "success": success,
            "latency_s": round(latency_s, 3),
            "output_len": output_len,
            "error": error,
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

async def _run_claude_via_sdk(
    prompt: str,
    model: str,
    workspace: str,
    timeout: int = 300,
    session_id: str = "",
    phase: str = "",
    thinking: str = "adaptive",
) -> tuple[int, str, float]:
    """Run Claude via agent SDK. Returns (returncode, output_text, cost_usd).

    Uses the same API pattern as board_meeting._run_prompt_via_sdk() (the verified Phase 1
    reference implementation). All standard Claude Code tools (Bash, Edit, Write, etc.) are
    available by default — no allowed_tools restriction so the generator can write files.

    thinking: "adaptive" (default — let Claude decide when to think deeply),
              "enabled" (always think, 8k token budget),
              "disabled" (no extended thinking).

    On any error or import failure, returns (1, "", 0.0) for transparent fallback to subprocess.
    Emits one row to .harness/agent-sdk-metrics/YYYY-MM-DD.jsonl on every invocation.
    """
    # RA-1099 — Hard policy gate. Map the call-site `phase` to a role and
    # assert the model is allowed for that role. Opus is reserved for Senior
    # PM (planner) + Senior Orchestrator. Any other role attempting opus
    # fails loudly here rather than running expensively in production.
    from .model_policy import assert_model_allowed  # noqa: PLC0415
    _role = (phase or "").split(".")[0] or "generator"
    try:
        assert_model_allowed(_role, model)
    except ValueError as policy_err:
        _log.error("RA-1099 model policy violation in _run_claude_via_sdk: %s", policy_err)
        raise

    try:
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )
        from claude_agent_sdk.types import (  # noqa: PLC0415
            ThinkingConfigAdaptive,
            ThinkingConfigEnabled,
            ThinkingConfigDisabled,
        )
    except ImportError as exc:
        # RA-576: SDK not installed but USE_AGENT_SDK=1 — deployment misconfiguration.
        # Raise so the operator sees it clearly rather than silently degrading to subprocess.
        _log.error(
            "claude_agent_sdk import failed but USE_AGENT_SDK=1. "
            "Install the package or set USE_AGENT_SDK=0. Error: %s", exc,
        )
        raise RuntimeError(
            "claude_agent_sdk not installed — set USE_AGENT_SDK=0 or run: pip install claude_agent_sdk"
        ) from exc

    # RA-659 — build thinking config
    _thinking_cfg: ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled | None
    if thinking == "adaptive":
        _thinking_cfg = ThinkingConfigAdaptive(type="adaptive")
    elif thinking == "enabled":
        _thinking_cfg = ThinkingConfigEnabled(type="enabled", budget_tokens=8000)
    else:
        _thinking_cfg = ThinkingConfigDisabled(type="disabled")

    t0 = time.monotonic()
    error_msg: Optional[str] = None
    output_text = ""
    try:
        # cwd=workspace so Claude edits files in the right directory.
        # No allowed_tools restriction — generator needs Bash + Edit + Write.
        # RA-1009 — prompt caching: pass beta flag when ENABLE_PROMPT_CACHING_1H=1.
        # The claude CLI forwards this beta to the Anthropic API, enabling server-side
        # cache reads on repeated sessions with the same static prompt prefix.
        _sdk_betas: list[str] = (
            ["prompt-caching-2024-07-31"]  # type: ignore[list-item]
            if config.ENABLE_PROMPT_CACHING_1H
            else []
        )
        # RA-1171 — Switch from ClaudeSDKClient to top-level query() per
        # Anthropic SDK issue #576 (https://github.com/anthropics/claude-agent-sdk-python/issues/576):
        # ClaudeSDKClient silently hangs when reused across FastAPI/ASGI
        # request tasks because the subprocess is spawned in task A's anyio
        # scope but subsequent receive_messages() calls run in task B whose
        # queue is owned by a dead task. We saw this as 8+ min of silence
        # in Phase 4 generator, zero AssistantMessage events, no error.
        #
        # Top-level query() is stateless — each call spawns a fresh
        # subprocess in the CURRENT task's scope and returns an async
        # iterator that terminates on ResultMessage. It's the documented
        # pattern for one-shot generation inside a request handler.
        #
        # RA-1169-adjacent — explicitly pop ANTHROPIC_API_KEY when empty.
        # The `claude` CLI sets it to "" in some contexts; SDK treats ""
        # as "use API key mode, key is empty" rather than falling back to
        # OAuth. Ensure it's genuinely absent so the SDK picks up the
        # `claude setup-token` credentials from ~/.claude/.
        if os.environ.get("ANTHROPIC_API_KEY") == "":
            os.environ.pop("ANTHROPIC_API_KEY", None)

        # RA-1172 — permission_mode='bypassPermissions' is MANDATORY for
        # autonomous sessions. Without it Claude hits tool-permission
        # prompts and emits text like "Let me know once permission is
        # granted and I'll handle the rest." — which looks to the evaluator
        # like an empty diff, causing Phase 5 to score 1/10 and retry
        # forever. CLAUDE.md documents this as the 3rd of 3 required
        # layers (settings.json + ClaudeAgentOptions + CLI flag).
        options = ClaudeAgentOptions(
            cwd=workspace,
            model=model,
            thinking=_thinking_cfg,
            betas=_sdk_betas,  # type: ignore[arg-type]
            permission_mode="bypassPermissions",
        )
        text_parts: list[str] = []

        # RA-1170 — enforce timeout on the async iterator. query() has no
        # built-in stream timeout (tracked upstream as SDK #666).
        async def _run_stream() -> None:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break

        await asyncio.wait_for(_run_stream(), timeout=timeout)
        output_text = "\n".join(text_parts)
        _write_sdk_metric(
            session_id=session_id, phase=phase, model=model,
            success=True, latency_s=time.monotonic() - t0,
            output_len=len(output_text),
        )
        return (0, output_text, 0.0)

    except asyncio.TimeoutError:
        error_msg = f"timeout after {timeout}s"
        _log.warning("SDK generator timed out after %ds", timeout)
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        _log.warning("SDK generator failed: %s (%s)", exc, type(exc).__name__)

    _write_sdk_metric(
        session_id=session_id, phase=phase, model=model,
        success=False, latency_s=time.monotonic() - t0,
        output_len=0, error=error_msg,
    )
    return (1, "", 0.0)
