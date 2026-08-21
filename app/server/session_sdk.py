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
from . import model_registry
from . import tool_gate

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


def _make_can_use_tool():
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
        decision = tool_gate.decide(tool_name, tool_input)
        if decision.allow:
            return PermissionResultAllow(updated_input=tool_input)
        _log.warning("tool gate DENY (%s): %s", decision.label, tool_name)
        _escalate_blocked_tool(decision.label, tool_name, decision.reason)
        return PermissionResultDeny(message=decision.reason, interrupt=False)

    return _can_use_tool


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
    output_tokens: Optional[int] = None,
    stop_reason: Optional[str] = None,
) -> None:
    """Append one SDK invocation row to today's JSONL metrics file.

    Non-blocking by design: any I/O error is silently swallowed so metrics
    failures never affect the build pipeline.

    RA-1099 Wave-3 — output_tokens (billed output from the ResultMessage usage)
    and stop_reason are captured so the fable-canary amplification metric
    (billed output tokens per 1K visible output chars) is computable per run;
    the kill-threshold is ~1100 tok / 1K visible chars on adversary runs.
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
            "output_tokens": output_tokens,
            "stop_reason": stop_reason,
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

    TODO(RA-1967): pre-pass through `app.server.tao_context_vcc.compact_for_sdk`
    once the SDK call surface accepts a structured message list. The current
    `prompt: str` shape would require parse → compact → re-render, which is a
    wider refactor than the Wave 1 primitive PR. Keep the wiring deferred until
    `tao-loop` (RA-1970) settles on the canonical TAO message representation.
    """
    # RA-1099 — Hard policy gate. Map the call-site `phase` to a role and
    # assert the model is allowed for that role. Opus is reserved for Senior
    # PM (planner) + Senior Orchestrator. Any other role attempting opus
    # fails loudly here rather than running expensively in production.
    from .model_policy import assert_model_allowed, effort_for_role  # noqa: PLC0415
    _role = (phase or "").split(".")[0] or "generator"

    # RA-1099 Wave-3 canary — env-gated fable tier (default OFF). When the role
    # is allow-listed via TAO_FABLE_ALLOWED_ROLES the effective model becomes
    # claude-fable-5; .harness/config.yaml keeps the role on 'opus', so flip-on
    # and revert are a single env-var change with zero code change. The adversary
    # phase passes model='opus' directly (it bypasses select_model), so the
    # override lives here — the single documented code path.
    _fable_canary = _role in config.FABLE_ALLOWED_ROLES
    if _fable_canary:
        model = model_registry.ANTHROPIC_FABLE

    try:
        assert_model_allowed(_role, model)
    except ValueError as policy_err:
        _log.error("RA-1099 model policy violation in _run_claude_via_sdk: %s", policy_err)
        raise
    # Wave 2 — thread the role's default effort level through to the SDK.
    _effort = effort_for_role(_role)

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

    _fable_id = model_registry.ANTHROPIC_FABLE

    async def _attempt(attempt_model: str):
        """Run one SDK query on attempt_model. Returns
        (rc, output_text, cost, stop_reason, output_tokens, error) and writes
        exactly one sdk-metric row. rc=1 on timeout, exception, OR a hard
        refusal (stop_reason == 'refusal', or empty output on the fable tier).
        """
        # RA-1099 Wave-3 PARAM STRIP — fable is adaptive-thinking-only; an
        # explicit budget_tokens/disabled config 400s. Force adaptive on the
        # fable tier regardless of the caller's `thinking` arg. No temperature/
        # top_p/top_k is ever built into ClaudeAgentOptions below, so nothing
        # else needs stripping for the fable path.
        _is_fable = attempt_model == _fable_id
        _thinking = "adaptive" if (_is_fable and thinking != "adaptive") else thinking

        # RA-659 — build thinking config
        _thinking_cfg: ThinkingConfigAdaptive | ThinkingConfigEnabled | ThinkingConfigDisabled | None
        if _thinking == "adaptive":
            _thinking_cfg = ThinkingConfigAdaptive(type="adaptive")
        elif _thinking == "enabled":
            _thinking_cfg = ThinkingConfigEnabled(type="enabled", budget_tokens=8000)
        else:
            _thinking_cfg = ThinkingConfigDisabled(type="disabled")

        t0 = time.monotonic()
        output_text = ""
        captured = {"stop_reason": None, "output_tokens": None}
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
            if (_k := os.environ.get("ANTHROPIC_API_KEY", "")) == "" or _k.startswith("sk-ant-oat01-"):
                os.environ.pop("ANTHROPIC_API_KEY", None)

            # RA-1172 — permission_mode='bypassPermissions' is MANDATORY for
            # autonomous sessions. Without it Claude hits tool-permission
            # prompts and emits text like "Let me know once permission is
            # granted and I'll handle the rest." — which looks to the evaluator
            # like an empty diff, causing Phase 5 to score 1/10 and retry
            # forever. CLAUDE.md documents this as the 3rd of 3 required
            # layers (settings.json + ClaudeAgentOptions + CLI flag).
            # RA — SDK-layer tool gate (TAO_TOOL_GATE). Default OFF keeps the proven
            # bypassPermissions path. When ON, route every tool call through
            # can_use_tool (requires streaming prompt + a non-bypass mode) so
            # recognised irreversible commands are denied inside the turn. The
            # callback decides autonomously — no human prompt — so RA-1172's
            # "waiting for permission" failure mode does not return.
            _gate_on = config.TAO_TOOL_GATE
            _opts: dict = dict(
                cwd=workspace,
                model=attempt_model,
                thinking=_thinking_cfg,
                effort=_effort,
                betas=_sdk_betas,  # type: ignore[arg-type]
                permission_mode="default" if _gate_on else "bypassPermissions",
                can_use_tool=_make_can_use_tool() if _gate_on else None,
                # The dedicated admission consumer credential is consumed and
                # removed from os.environ at server startup. Keep an explicit
                # empty override as defence in depth because the Agent SDK
                # subprocess otherwise inherits the parent process environment.
                env={"SENIOR_HARNESS_ADMISSION_CONSUMER_TOKEN": ""},
            )
            if _gate_on:
                # Pin setting_sources to [] so no filesystem allow-rule (e.g. a
                # `Bash(*)` entry in ~/.claude/settings.json) can be consulted
                # before can_use_tool and silently turn the gate into a no-op for
                # exactly the commands it guards.
                _opts["setting_sources"] = []
            options = ClaudeAgentOptions(**_opts)
            _prompt_arg = _tool_gate_stream(prompt, session_id) if _gate_on else prompt
            text_parts: list[str] = []

            # RA-1170 — enforce timeout on the async iterator. query() has no
            # built-in stream timeout (tracked upstream as SDK #666).
            # RA-1099 Wave-3 STOP-REASON GUARD + AMPLIFICATION — capture
            # stop_reason and billed output_tokens off the Assistant/Result
            # messages so a hard refusal is visible (not silently success) and
            # billed-output-per-1K-visible-chars is computable per run.
            async def _run_stream() -> None:
                async for msg in query(prompt=_prompt_arg, options=options):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                text_parts.append(block.text)
                        _sr = getattr(msg, "stop_reason", None)
                        if _sr is not None:
                            captured["stop_reason"] = _sr
                        _ot = _usage_output_tokens(getattr(msg, "usage", None))
                        if _ot is not None:
                            captured["output_tokens"] = _ot
                    elif isinstance(msg, ResultMessage):
                        _sr = getattr(msg, "stop_reason", None)
                        if _sr is not None:
                            captured["stop_reason"] = _sr
                        _ot = _usage_output_tokens(getattr(msg, "usage", None))
                        if _ot is not None:
                            captured["output_tokens"] = _ot
                        break

            await asyncio.wait_for(_run_stream(), timeout=timeout)
            output_text = "\n".join(text_parts)
            _stop = captured["stop_reason"]
            _out_tok = captured["output_tokens"]

            # STOP-REASON GUARD — a hard refusal (or empty output on the fable
            # tier) is a FAILURE, not silent success. Emit an explicit metric and
            # return the failure tuple so the caller (and the fable→opus fallback
            # below) never greenlights an empty/partial review.
            _refused = _stop == "refusal"
            _empty_fable = _is_fable and not output_text.strip()
            if _refused or _empty_fable:
                _err = "refusal" if _refused else "empty_output_fable"
                _write_sdk_metric(
                    session_id=session_id, phase=phase, model=attempt_model,
                    success=False, latency_s=time.monotonic() - t0,
                    output_len=len(output_text), output_tokens=_out_tok,
                    stop_reason=_stop, error=_err,
                )
                return (1, "", 0.0, _stop, _out_tok, _err)

            _write_sdk_metric(
                session_id=session_id, phase=phase, model=attempt_model,
                success=True, latency_s=time.monotonic() - t0,
                output_len=len(output_text), output_tokens=_out_tok,
                stop_reason=_stop,
            )
            return (0, output_text, 0.0, _stop, _out_tok, None)

        except asyncio.TimeoutError:
            error_msg = f"timeout after {timeout}s"
            _log.warning("SDK generator timed out after %ds", timeout)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            _log.warning("SDK generator failed: %s (%s)", exc, type(exc).__name__)

        _write_sdk_metric(
            session_id=session_id, phase=phase, model=attempt_model,
            success=False, latency_s=time.monotonic() - t0,
            output_len=0, output_tokens=captured["output_tokens"],
            stop_reason=captured["stop_reason"], error=error_msg,
        )
        return (1, "", 0.0, captured["stop_reason"], captured["output_tokens"], error_msg)

    rc, text, cost, _stop, _out_tok, _err = await _attempt(model)

    # RA-1099 Wave-3 ERROR-PATH FALLBACK — the Board requires that a fable
    # refusal OR a fable unavailability error retries the SAME call on
    # claude-opus-5 before giving up, so the adversary pre-push gate never
    # silently passes on an errored/refused review. One-shot retry only.
    if model == _fable_id and rc != 0:
        _log.warning(
            "fable canary attempt failed (stop_reason=%s error=%s) — "
            "falling back to %s for role=%s",
            _stop, _err, config.MODEL_ID_OPUS, _role,
        )
        rc, text, cost, _stop, _out_tok, _err = await _attempt(config.MODEL_ID_OPUS)

    # RA-7216 gap 4 — route this invocation's spend to the durable llm_costs
    # table. Until now the Agent SDK path recorded cost ONLY to
    # .harness/agent-sdk-metrics/, which is gitignored and lives on ephemeral
    # Railway disk, so generator and evaluator spend — the dominant cost of a
    # build — was lost on every redeploy and never reached llm_costs. Cost per
    # accepted outcome computed from that table was therefore biased far low,
    # counting only the cheap-tier provider_router calls.
    #
    # record_cost is fire-and-forget by contract and must not raise into the
    # SDK path; the try/except is belt-and-braces for the import itself.
    try:
        from swarm.budget_tracker import record_cost  # noqa: PLC0415

        record_cost(
            provider="anthropic_agent_sdk",
            role=_role or "",
            model=model,
            cost_usd=float(cost or 0.0),
            tokens_in=0,          # the SDK usage payload exposes billed output
            tokens_out=int(_out_tok or 0),   # tokens only; in-tokens stay 0 rather
        )                                    # than being guessed.
    except Exception as exc:  # noqa: BLE001
        _log.debug("RA-7216 SDK cost record failed (non-fatal): %s", exc)

    return (rc, text, cost)
