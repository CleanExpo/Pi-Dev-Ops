"""Cross-channel rolling execution horizon for Mission Control.

Keeps one canonical objective and up to 15 next moves visible across Claude,
Telegram, Slack and Mission Control. This module is intentionally policy-only:
it never bypasses approval, kill-switch, spend, deploy, merge, delete or other
protected-action gates. It exists to stop safe work from ending merely because
one sub-task completed.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HORIZON_TARGET = 15
STATE_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path() -> Path:
    root = Path(os.environ.get("TAO_DATA_DIR") or os.environ.get("DATA_DIR") or ".harness")
    root.mkdir(parents=True, exist_ok=True)
    return root / "continuation-horizon.json"


def load_state() -> dict[str, Any]:
    path = state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    state = {**state, "version": STATE_VERSION, "updated_at": _now()}
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def arm_objective(*, objective: str, source: str, chat_id: str = "") -> dict[str, Any]:
    current = load_state()
    objective = objective.strip()
    if not objective:
        return current
    state = {
        **current,
        "armed": True,
        "objective": objective,
        "source": source,
        "chat_id": chat_id or current.get("chat_id", ""),
        "completed": False,
        "completion_evidence": [],
        "horizon_target": HORIZON_TARGET,
        "last_progress_at": _now(),
    }
    save_state(state)
    return state


def set_horizon(steps: list[dict[str, Any]]) -> dict[str, Any]:
    state = load_state()
    clean: list[dict[str, Any]] = []
    for index, step in enumerate(steps[:HORIZON_TARGET], 1):
        if not isinstance(step, dict):
            continue
        title = str(step.get("title") or step.get("step") or "").strip()
        if not title:
            continue
        clean.append({
            "id": str(step.get("id") or index),
            "title": title,
            "status": str(step.get("status") or "pending"),
            "depends_on": [str(x) for x in (step.get("depends_on") or [])],
            "protected": bool(step.get("protected", False)),
            "evidence": step.get("evidence") or [],
        })
    state["steps"] = clean
    state["last_progress_at"] = _now()
    save_state(state)
    return state


def ready_steps() -> list[dict[str, Any]]:
    state = load_state()
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    done = {str(s.get("id")) for s in steps if s.get("status") in {"done", "verified", "complete"}}
    return [
        s for s in steps
        if s.get("status") == "pending"
        and all(str(dep) in done for dep in (s.get("depends_on") or []))
        and not bool(s.get("protected"))
    ]


def mark_step(step_id: str, status: str, evidence: list[str] | None = None) -> dict[str, Any]:
    state = load_state()
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    for step in steps:
        if str(step.get("id")) == str(step_id):
            step["status"] = status
            if evidence:
                step["evidence"] = list(evidence)
            break
    state["steps"] = steps
    state["last_progress_at"] = _now()
    save_state(state)
    return state


def mark_complete(evidence: list[str] | None = None) -> dict[str, Any]:
    state = load_state()
    state["armed"] = False
    state["completed"] = True
    state["completed_at"] = _now()
    state["completion_evidence"] = list(evidence or [])
    save_state(state)
    return state


def should_continue() -> bool:
    state = load_state()
    if not state.get("armed") or state.get("completed"):
        return False
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    if not steps:
        return True
    return any(s.get("status") not in {"done", "verified", "complete", "blocked_protected"} for s in steps)


def operator_context() -> str:
    state = load_state()
    objective = str(state.get("objective") or "").strip()
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    pending = [s for s in steps if s.get("status") not in {"done", "verified", "complete"}]
    lines = [
        "MISSION CONTROL CONTINUATION CONTRACT:",
        f"- Maintain a rolling horizon of up to {HORIZON_TARGET} concrete next moves.",
        "- Execute dependency-safe, reversible moves in parallel where practical.",
        "- Refill the horizon before it empties; finishing one task is not completion.",
        "- Continue safe work without asking for another human prompt.",
        "- Protected actions remain gated; mark them blocked_protected and continue other safe lanes.",
        "- Stop only when the objective is verified complete, a real safety/authority boundary blocks all useful work, or the kill switch is active.",
    ]
    if objective:
        lines.append(f"- Current objective: {objective}")
    if pending:
        lines.append("- Current pending horizon: " + " | ".join(str(s.get("title")) for s in pending[:HORIZON_TARGET]))
    return "\n".join(lines)
