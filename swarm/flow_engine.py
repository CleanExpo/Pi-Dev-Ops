"""
swarm/flow_engine.py — RA-1839: Cross-tool workflow primitive (dispatcher-core).

Executes ordered, declarative flows that chain skills + MCP tools.
State persisted to .harness/swarm/dispatcher_state.json keyed by flow_id.

Engine guarantees:
  * No unbounded recursion (sub-flows rejected in Wave 2)
  * Tool allowlist enforced per-flow
  * Kill-switch aware (TAO_SWARM_ENABLED)
  * Audit immutable (.harness/swarm/swarm.jsonl)
  * Templating is data, not code (no exec, no shell-out)

Tool resolution: callers register tools via `register_tool(name, callable)`.
A small built-in set is registered automatically:
  * `skill.intent-parser` → swarm.intent_router.classify
  * `skill.telegram-draft-for-review` → swarm.draft_review.post_draft
  * `skill.pii-redactor` → swarm.pii_redactor.redact
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger("swarm.flow_engine")

OnError = Literal["abort", "log_and_continue", "retry_3x"]

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.\-]+)\s*\}\}")

# Registry of tool callables: name → callable(**kwargs) → dict
_TOOL_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_tool(name: str, fn: Callable[..., Any]) -> None:
    """Register a tool by name. Skill names use 'skill.<name>'; MCP use 'mcp.<server>.<tool>'."""
    if name in _TOOL_REGISTRY:
        log.debug("tool %s re-registered", name)
    _TOOL_REGISTRY[name] = fn


def _builtins() -> None:
    """Register Wave 1/2 internal tools at import time."""
    try:
        from . import intent_router
        register_tool("skill.intent-parser",
                     lambda **kw: intent_router.classify(**kw))
    except Exception as exc:
        log.debug("intent_router not registrable: %s", exc)
    try:
        from . import draft_review
        register_tool("skill.telegram-draft-for-review",
                     lambda **kw: draft_review.post_draft(**kw))
    except Exception as exc:
        log.debug("draft_review not registrable: %s", exc)
    try:
        from . import pii_redactor
        register_tool("skill.pii-redactor",
                     lambda **kw: pii_redactor.redact(**kw).__dict__
                     if hasattr(pii_redactor.redact(**kw), "__dict__") else
                     pii_redactor.redact(**kw))
    except Exception as exc:
        log.debug("pii_redactor not registrable: %s", exc)


_builtins()


def _config():
    from . import config as _cfg
    return _cfg


def _state_dir() -> Path:
    cfg = _config()
    cfg.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.SWARM_LOG_DIR


def _state_file() -> Path:
    return _state_dir() / "dispatcher_state.json"


def _audit_file() -> Path:
    return _state_dir() / "swarm.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_audit(row: dict[str, Any]) -> None:
    """DEPRECATED — kept only for callers not yet migrated. Routes through
    audit_emit when type is in the whitelist; falls back to direct write
    otherwise. Remove once every internal caller uses audit_emit.row().
    """
    try:
        from . import audit_emit
        if row.get("type") in audit_emit._VALID_TYPES:
            kwargs = {k: v for k, v in row.items()
                     if k not in ("ts", "type", "actor_role")}
            audit_emit.row(row["type"],
                          row.get("actor_role", "Dispatcher"),
                          **kwargs)
            return
    except Exception:
        pass
    with _audit_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_state() -> dict[str, dict[str, Any]]:
    p = _state_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_state(state: dict[str, dict[str, Any]]) -> None:
    p = _state_file()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def _resolve_template(value: Any, state: dict[str, Any]) -> Any:
    """Resolve {{ctx.X}} / {{step_id.output.X}} / {{env.X}} / built-ins."""
    if isinstance(value, dict):
        return {k: _resolve_template(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_template(v, state) for v in value]
    if not isinstance(value, str):
        return value

    def _sub(m: re.Match) -> str:
        path = m.group(1)
        return str(_lookup(path, state))

    return _TEMPLATE_RE.sub(_sub, value)


def _lookup(path: str, state: dict[str, Any]) -> Any:
    head, _, rest = path.partition(".")
    if head == "ctx":
        return _walk(state.get("context", {}), rest)
    if head == "env":
        return os.environ.get(rest, "")
    if head == "utc_now":
        return _now_iso()
    if head == "date":
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # step_id.output.X
    step_state = state.get("step_state", {}).get(head, {})
    if rest.startswith("output."):
        return _walk(step_state.get("output", {}), rest[len("output."):])
    return _walk(step_state, rest)


def _walk(obj: Any, path: str) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except Exception:
                return None
        else:
            return getattr(obj, part, None)
    return obj


def _kill_switch_active() -> bool:
    return os.environ.get("TAO_SWARM_ENABLED", "0") != "1"


def validate_flow(flow: dict[str, Any]) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors: list[str] = []
    if "name" not in flow:
        errors.append("missing name")
    steps = flow.get("steps") or []
    if not steps:
        errors.append("no steps")
    allowlist = set(flow.get("tool_allowlist") or [])
    seen_ids = set()
    for i, step in enumerate(steps):
        sid = step.get("id")
        if not sid:
            errors.append(f"step[{i}] missing id")
            continue
        if sid in seen_ids:
            errors.append(f"duplicate step id: {sid}")
        seen_ids.add(sid)
        tool = step.get("tool")
        if not tool:
            errors.append(f"step {sid}: missing tool")
            continue
        if tool not in _TOOL_REGISTRY:
            errors.append(f"step {sid}: unknown tool {tool}")
        if allowlist and tool not in allowlist:
            errors.append(f"step {sid}: tool {tool} not in tool_allowlist")
        for dep in step.get("depends_on") or []:
            if dep not in seen_ids:
                errors.append(f"step {sid}: depends_on {dep} comes after this step")
    return errors


def execute_flow(
    flow: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a flow synchronously. Returns final state record.

    `dry_run=True` validates + logs the plan but does NOT call any tool.
    """
    errors = validate_flow(flow)
    if errors:
        raise ValueError(f"flow validation failed: {errors}")

    flow_id = flow.get("flow_id") or uuid.uuid4().hex[:12]
    name = flow["name"]
    steps = flow["steps"]

    state: dict[str, Any] = {
        "flow_id": flow_id,
        "name": name,
        "started_at": _now_iso(),
        "status": "running",
        "context": dict(context or {}),
        "step_state": {s["id"]: {"status": "pending"} for s in steps},
    }

    snap = _load_state()
    snap[flow_id] = state
    _save_state(snap)
    from . import audit_emit
    audit_emit.row("flow_start", "Dispatcher",
                   flow_id=flow_id, name=name, dry_run=dry_run)

    for step in steps:
        if _kill_switch_active() and not dry_run:
            state["status"] = "paused"
            state[step["id"] + "_paused_at"] = _now_iso()
            log.info("flow %s paused mid-run by kill-switch", flow_id)
            break

        sid = step["id"]
        ss = state["step_state"][sid]
        ss["started_at"] = _now_iso()
        ss["status"] = "running"
        snap[flow_id] = state
        _save_state(snap)
        audit_emit.row("step_start", "Dispatcher",
                       flow_id=flow_id, step_id=sid, tool=step["tool"])

        if dry_run:
            ss["status"] = "skipped_dry_run"
            ss["completed_at"] = _now_iso()
            ss["output"] = {"_dry_run": True}
            audit_emit.row("step_complete", "Dispatcher",
                           flow_id=flow_id, step_id=sid, dry_run=True)
            continue

        args = _resolve_template(step.get("args") or {}, state)
        tool = _TOOL_REGISTRY[step["tool"]]
        on_error: OnError = step.get("on_error", "abort")

        try:
            output = tool(**args) if isinstance(args, dict) else tool(args)
        except Exception as exc:
            ss["status"] = "error"
            ss["error"] = repr(exc)
            ss["completed_at"] = _now_iso()
            audit_emit.row("step_error", "Dispatcher",
                           flow_id=flow_id, step_id=sid,
                           error=repr(exc), on_error=on_error)
            if on_error == "abort":
                state["status"] = "failed"
                snap[flow_id] = state
                _save_state(snap)
                return state
            else:
                continue

        ss["status"] = "completed"
        ss["completed_at"] = _now_iso()
        ss["output"] = output if isinstance(output, (dict, list, str, int, float, bool, type(None))) else str(output)
        snap[flow_id] = state
        _save_state(snap)
        audit_emit.row("step_complete", "Dispatcher",
                       flow_id=flow_id, step_id=sid)

    if state["status"] == "running":
        state["status"] = "completed"
        state["completed_at"] = _now_iso()

    snap[flow_id] = state
    _save_state(snap)
    audit_emit.row("flow_end", "Dispatcher",
                   flow_id=flow_id, status=state["status"])
    return state


__all__ = ["register_tool", "validate_flow", "execute_flow"]
