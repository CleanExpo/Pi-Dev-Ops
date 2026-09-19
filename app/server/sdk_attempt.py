"""One SDK attempt: strict options, streamed evidence, and bounded execution."""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import logging
import math
import time

from . import config, model_registry, planner_admission
from .sdk_execution_boundary import ExecutionBoundaryError, _cli_identity

_log = logging.getLogger("pi-ceo.session_sdk")


class SDKAttempt:
    def __init__(self, *, prompt, model, workspace, timeout, session_id, phase,
                 thinking, effort, execution_options, cli_identity, metric, stream):
        self.prompt, self.model, self.workspace = prompt, model, workspace
        self.timeout, self.session_id, self.phase = timeout, session_id, phase
        self.thinking, self.effort = thinking, effort
        self.execution_options, self.cli_identity = execution_options, cli_identity
        self.metric, self.stream = metric, stream
        self.role = (phase or "").split(".")[0] or "generator"
        self.started = time.monotonic()
        self.parts, self.observed = [], set()
        self.cost, self.stop, self.output_tokens, self.input_tokens = None, None, None, None
        self.result_seen, self.result_error = False, False

    def options(self):
        from claude_agent_sdk import ClaudeAgentOptions
        from .provider_policy import require_transport
        require_transport("anthropic_agent_sdk", cli_path=self.execution_options["cli_path"],
                          env=self.execution_options["env"])
        if _cli_identity(self.execution_options["cli_path"]) != self.cli_identity:
            raise ExecutionBoundaryError("execution_blocked: CLI changed after version verification")
        fable = self.model == model_registry.ANTHROPIC_FABLE
        mode = planner_admission.planner_thinking_mode(
            self.phase, "adaptive" if fable else self.thinking, is_fable=fable)
        from claude_agent_sdk.types import ThinkingConfigAdaptive, ThinkingConfigEnabled, ThinkingConfigDisabled
        thinking = ThinkingConfigAdaptive(type="adaptive") if mode == "adaptive" else ThinkingConfigDisabled(type="disabled")
        if mode == "enabled":
            thinking = ThinkingConfigEnabled(type="enabled", budget_tokens=8000)
        opts = dict(cwd=self.workspace, model=self.model, thinking=thinking, effort=self.effort,
                    betas=["prompt-caching-2024-07-31"] if config.ENABLE_PROMPT_CACHING_1H else [],
                    **self.execution_options)
        planner_admission.apply_planner_agent_options(opts, self.phase)
        # No compatibility filtering: silently dropping sandbox/env/cli is unsafe.
        try:
            return ClaudeAgentOptions(**opts)
        except TypeError as exc:
            raise ExecutionBoundaryError("execution_blocked: installed SDK cannot preserve required execution options") from exc

    def capture_usage(self, msg):
        stop = getattr(msg, "stop_reason", None)
        if stop is not None:
            self.stop = stop
        usage = getattr(msg, "usage", None)
        output = usage.get("output_tokens") if isinstance(usage, dict) else getattr(usage, "output_tokens", None)
        if output is not None:
            self.output_tokens = output
        if isinstance(usage, dict):
            self.input_tokens = usage.get("input_tokens")

    def capture_result(self, msg):
        self.result_seen = True
        self.result_error = (getattr(msg, "is_error", False) is True
                             or str(getattr(msg, "subtype", "")).startswith("error"))
        cost = getattr(msg, "total_cost_usd", None)
        if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
            self.cost = float(cost)
        usage = getattr(msg, "model_usage", None)
        if isinstance(usage, dict):
            self.observed.update(name.strip() for name in usage if isinstance(name, str) and name.strip())
        self.capture_usage(msg)

    async def consume(self, options):
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query
        async with aclosing(query(prompt=self.stream(self.prompt, self.session_id), options=options)) as messages:
            async for msg in messages:
                if isinstance(msg, AssistantMessage):
                    model = getattr(msg, "model", None)
                    if isinstance(model, str) and model.strip():
                        self.observed.add(model.strip())
                    self.parts.extend(block.text for block in msg.content if isinstance(block, TextBlock))
                    self.capture_usage(msg)
                elif isinstance(msg, ResultMessage):
                    self.capture_result(msg)
                    break

    def record(self, success, error=None):
        actual = next(iter(self.observed)) if len(self.observed) == 1 else None
        self.metric(session_id=self.session_id, phase=self.phase, model=self.model,
                    requested_model=self.model, actual_model=actual, observed_models=sorted(self.observed),
                    model_verified=actual is not None, cost_usd=self.cost,
                    cost_source="sdk_reported_usage" if self.cost is not None else "unknown",
                    cost_verified=False, success=success, latency_s=time.monotonic() - self.started,
                    output_len=len("\n".join(self.parts)), output_tokens=self.output_tokens,
                    stop_reason=self.stop, error=error)
        if self.cost is not None:
            try:
                from swarm.budget_tracker import record_cost
                record_cost(provider="anthropic_agent_sdk", role=self.role, model=actual or "unknown",
                            cost_usd=self.cost, tokens_in=int(self.input_tokens or 0),
                            tokens_out=int(self.output_tokens or 0))
            except Exception as exc:
                _log.debug("SDK reported usage record failed (non-fatal): %s", exc)

    def completed(self):
        if not self.result_seen or self.result_error:
            raise ExecutionBoundaryError("execution_blocked: SDK did not report successful execution; sandbox setup or run failed")
        text = "\n".join(self.parts)
        error = "refusal" if self.stop == "refusal" else None
        if self.model == model_registry.ANTHROPIC_FABLE and not text.strip():
            error = error or "empty_output_fable"
        self.record(error is None, error)
        return (1 if error else 0, error or text, self.cost, self.stop, self.output_tokens, error)

    async def run(self):
        from .provider_policy import ProviderPolicyError
        try:
            options = self.options()
            # Preserve Main's registry-scoped workspace trust integration without
            # mutating ambient authentication variables after policy verification.
            from .claude_workspace_trust import ensure_workspace_trusted
            await asyncio.to_thread(ensure_workspace_trusted, self.workspace)
            await asyncio.wait_for(self.consume(options), timeout=self.timeout)
            return self.completed()
        except asyncio.CancelledError:
            self.record(False, "cancelled")
            raise
        except asyncio.TimeoutError:
            error = f"timeout after {self.timeout}s"
        except (ProviderPolicyError, ExecutionBoundaryError) as exc:
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        self.record(False, error)
        return (1, error, self.cost, self.stop, self.output_tokens, error)
