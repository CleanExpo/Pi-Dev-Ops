"""Policy-checked dispatch, separated from model selection."""
from __future__ import annotations
import asyncio
import json
import os
import threading
from . import provider_policy
from . import provider_process_tree as _tree
from .provider_execution_types import ProviderExecution

CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")
STOPPED_RC = 130  # the caller's stop signal ended the call; nothing usable was produced
_STOP_POLL_S = 0.25
_TERM_GRACE_S = 2.0
_STOP_BUDGET_S = 2.5  # freeze, record, terminate, kill and check; then at most _DRAIN_S of draining
_DRAIN_S = 1.5

async def _run_via_claude_print(
    prompt: str, *, model_id: str, timeout_s: int = 120,
    provenance: dict | None = None, stop: threading.Event | None = None,
) -> ProviderExecution:
    """Run a tool-free subscription CLI call and retain its reported model."""
    evidence = dict(provenance or {})
    evidence.update(provider="anthropic", transport="claude_print", requested_model=model_id,
                    actual_model=None, model_verified=False)

    args = (prompt, model_id, timeout_s) + ((stop,) if stop is not None else ())
    rc, stdout, stderr = await asyncio.to_thread(_claude_process, *args)
    if rc == STOPPED_RC and stop is not None and stop.is_set():
        return ProviderExecution(rc, "", None, "claude_print_stopped", evidence)
    if rc != 0:
        return ProviderExecution(rc, "", None, f"claude_print_failed: exit {rc}", evidence)
    try:
        payload = json.loads(stdout)
        if not isinstance(payload, dict) or payload.get("type") != "result" or payload.get("is_error") is not False:
            raise ValueError("invalid or failed result")
        text = payload.get("result")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty result")
        models = payload.get("modelUsage")
        if isinstance(models, dict) and len(models) == 1:
            actual = next(iter(models))
            if isinstance(actual, str) and actual.strip():
                evidence.update(actual_model=actual, model_verified=True,
                                model_source="claude_result.modelUsage")
        # total_cost_usd in CLI output is a usage estimate, not a subscription invoice.
        return ProviderExecution(0, text.strip(), None, None, evidence)
    except (ValueError, TypeError):
        return ProviderExecution(1, "", None, "claude_print_invalid_result", evidence)


async def _run_via_codex(prompt: str, *, model_id: str, timeout_s: int,
                         provenance: dict, stop: threading.Event | None = None) -> ProviderExecution:
    """Supported ChatGPT CLI path; JSONL currently lacks served-model evidence.

    See OpenAI Codex issue #39406. Requested/configured model is never used as
    a substitute. Such output is useful advice but cannot pass a release audit.
    """
    import subprocess
    evidence = dict(provenance, provider="openai", transport="codex", requested_model=model_id,
                    actual_model=None, model_verified=False)

    try:
        args = (prompt, model_id, timeout_s) + ((stop,) if stop is not None else ())
        completed = await asyncio.to_thread(_codex_process, *args)
        if completed.returncode == STOPPED_RC and stop is not None and stop.is_set():
            return ProviderExecution(STOPPED_RC, "", None, "codex_stopped", evidence)
        if completed.returncode != 0:
            return ProviderExecution(1, "", None, "codex_execution_failed", evidence)
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        if any(not isinstance(event, dict) or event.get("type") in {"turn.failed", "error"} for event in events):
            raise ValueError("failed event")
        if not any(event.get("type") == "turn.completed" for event in events):
            raise ValueError("completion missing")
        messages = [event["item"]["text"] for event in events
                    if event.get("type") == "item.completed"
                    and isinstance(event.get("item"), dict)
                    and event["item"].get("type") == "agent_message"
                    and isinstance(event["item"].get("text"), str)]
        if not messages or not messages[-1].strip():
            raise ValueError("message missing")
        return ProviderExecution(0, messages[-1].strip(), None, None, evidence)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ProviderExecution(1, "", None, "codex_result_unavailable", evidence)


async def run_via_provider_with_evidence(prompt: str, *, role: str,
                                       task_class: str = "default", timeout_s: int = 120,
                                       workspace: str | None = None, session_id: str = "",
                                       thinking: str = "adaptive", confidential: bool = False,
                                       stop: threading.Event | None = None) -> ProviderExecution:
    extra = {"stop": stop} if stop is not None else {}  # optional; see _run_stoppable
    from .provider_router import select_provider_model, _record_cost_safe
    pm = select_provider_model(role, task_class=task_class)
    evidence = {"provider": pm.provider, "requested_model": pm.model_id,
                "actual_model": None, "model_verified": False, "auth_verified": False,
                "billing_class": "unknown", "source": "provider_router"}
    try:
        if confidential and pm.provider != "ollama":
            raise provider_policy.ProviderPolicyError("subscription_only: confidential task requires local transport")
        evidence.update(await asyncio.to_thread(provider_policy.require_transport, pm.provider))
    except provider_policy.ProviderPolicyError as exc:
        return ProviderExecution(1, "", None, str(exc), evidence)
    if pm.provider == "claude_print":
        return await _run_via_claude_print(prompt, model_id=pm.model_id,
                                          timeout_s=timeout_s, provenance=evidence, **extra)
    if pm.provider == "codex":
        return await _run_via_codex(prompt, model_id=pm.model_id,
                                    timeout_s=timeout_s, provenance=evidence, **extra)
    # Dispatch the same selection that passed policy; do not re-resolve it.
    try:
        import sys
        adapter = sys.modules.get("app.server.provider_ollama")
        if adapter is None:
            from . import provider_ollama as adapter
        outcome = await adapter.call_with_evidence(
            prompt=prompt, model_id=pm.model_id, timeout_s=timeout_s,
            role=role, session_id=session_id,
        )
    except Exception:
        return ProviderExecution(1, "", None, "ollama_call_failed", evidence)
    if outcome.rc == 0:
        _record_cost_safe(provider="ollama", role=role,
                          model=outcome.provenance.get("actual_model") or "unknown",
                          cost_usd=outcome.cost_usd or 0.0)
    return outcome


async def run_via_provider(prompt: str, **kwargs) -> tuple[int, str, float | None, str | None]:
    """Compatible four-value surface; unknown cost is None, never invented zero."""
    from .provider_margot_casual import MARGOT_CASUAL_ROLE, _run_margot_casual
    if kwargs.get("role") == MARGOT_CASUAL_ROLE and not kwargs.get("confidential"):
        return await _run_margot_casual(
            prompt, timeout_s=kwargs.get("timeout_s", 120),
            session_id=kwargs.get("session_id", ""),
        )
    return (await run_via_provider_with_evidence(prompt, **kwargs)).as_tuple()




def _claude_process(prompt, model_id, timeout_s, stop=None) -> tuple[int, str, str]:
    import subprocess as _sp  # noqa: PLC0415
    argv = [CLAUDE_CLI, "--print", prompt, "--model", model_id,
            "--output-format", "json", "--tools", "", "--setting-sources", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    try:
        if stop is not None:
            rc, out, err = _run_stoppable(argv, stop=stop, timeout_s=timeout_s)
            if rc == 124:
                return 124, "", f"claude --print timed out after {timeout_s}s"
            return rc, out, err
        r = _sp.run(
            argv,
            capture_output=True, text=True, timeout=timeout_s, check=False,
            creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"claude CLI not found at {CLAUDE_CLI}"
    except _sp.TimeoutExpired:
        return 124, "", f"claude --print timed out after {timeout_s}s"



def _codex_process(prompt, model_id, timeout_s, stop=None):
    import subprocess
    import tempfile
    # An empty directory prevents project hooks/config or local instructions
    # from altering this bounded review of the supplied prompt.
    with tempfile.TemporaryDirectory(prefix="pidev-review-") as directory:
        argv = [os.environ.get("CODEX_CLI", "codex"), "exec", "--json", "--ephemeral",
             "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
             "--sandbox", "read-only", "--model", model_id,
             "--config", 'model_provider="openai"',
             "--config", 'forced_login_method="chatgpt"',
             "--config", 'approval_policy="never"',
             "--config", "features.shell_tool=false",
             "--config", 'web_search="disabled"',
             "--config", 'shell_environment_policy.inherit="none"', "-"]
        if stop is not None:
            rc, out, err = _run_stoppable(argv, stop=stop, timeout_s=timeout_s,
                                          input=prompt, cwd=directory)
            if rc == 124:
                raise subprocess.TimeoutExpired(argv, timeout_s)
            return subprocess.CompletedProcess(argv, rc, out, err)
        return subprocess.run(
            argv,
            input=prompt, cwd=directory, capture_output=True, text=True,
            timeout=timeout_s, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def _end_group(proc, known: dict[int, str] | None = None) -> None:
    """End the CLI, its process group and every descendant recorded from the process tree.

    A descendant that called setsid() is outside the group, so it is stopped by pid; anything
    still alive afterwards, or an unreadable process list, is logged as a warning.
    """
    import subprocess as _sp  # noqa: PLC0415
    if os.name != "posix":
        proc.terminate()
        try:
            proc.wait(timeout=_TERM_GRACE_S)
        except _sp.TimeoutExpired:
            proc.kill()
        return
    fds = [f.fileno() for f in (proc.stdout, proc.stderr) if f is not None and not f.closed]
    _tree.stop_tree(proc, dict(known or {}), budget_s=_STOP_BUDGET_S, grace_s=_TERM_GRACE_S, fds=fds)


def _drain(proc) -> tuple[str, str]:
    """Collect what the ended group wrote, but never wait on a descendant that left the group.

    A child that called setsid() is outside the process group, so killpg cannot reach it; if it
    still holds the output pipes, close them after the grace period instead of blocking the stop.
    """
    import subprocess as _sp  # noqa: PLC0415
    try:
        out, err = proc.communicate(timeout=_DRAIN_S)
        return out or "", err or ""
    except _sp.TimeoutExpired:
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        proc.wait()
        return "", "a descendant outside the process group kept the output open; it was not waited for"


def _run_stoppable(argv, *, stop, timeout_s, input=None, cwd=None) -> tuple[int, str, str]:
    """Run in a new process group; end the group on stop (rc 130) or deadline (rc 124).

    Only callers that pass a stop event reach this path; everyone else keeps subprocess.run.
    A stop set before the start, or before a finished result is accepted, also returns rc 130.
    HTTP transports (ollama) ignore stop and keep their own timeouts.
    """
    import subprocess as _sp  # noqa: PLC0415
    import time as _time  # noqa: PLC0415
    if stop.is_set():
        return STOPPED_RC, "", "stopped before the call started"
    proc = _sp.Popen(argv, stdin=_sp.PIPE if input is not None else _sp.DEVNULL,
                     stdout=_sp.PIPE, stderr=_sp.PIPE, text=True, cwd=cwd,
                     start_new_session=os.name == "posix",
                     creationflags=getattr(_sp, "CREATE_NEW_PROCESS_GROUP", 0))
    deadline, pending, known = _time.monotonic() + timeout_s, input, {}
    while True:
        remaining = deadline - _time.monotonic()
        reason = STOPPED_RC if stop.is_set() else 124 if remaining <= 0 else 0
        if reason:
            _end_group(proc, known)
            return reason, "", _drain(proc)[1]  # a stopped or timed-out call yields no output
        try:  # never wait past the deadline, so a late result cannot be accepted
            out, err = proc.communicate(pending, timeout=min(_STOP_POLL_S, remaining))
        except _sp.TimeoutExpired:
            pending = None
            known.update(_tree.descendants(proc.pid, 0.5) or {})  # seen while the tree is intact
            continue
        if stop.is_set():  # a stopped call's result is never accepted; end any children left
            _end_group(proc, known)
            return STOPPED_RC, "", err or ""
        return proc.returncode, out, err
