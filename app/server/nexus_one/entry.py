"""Margot accept/resume and method attempts for the synthetic pilot."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable

from .store import SyntheticStore
from .types import (
    SYNTHETIC_FIXTURE_ID,
    SYNTHETIC_MARKER,
    MethodAttempt,
    TaskContract,
)

DEFAULT_AUTHORISED = frozenset({"phill", "founder"})
MAX_OBJECTIVE_CHARS = 500
DEFAULT_METHOD = "synthetic-complete"
DEFAULT_HYPOTHESIS = "bounded synthetic fixture emits scoped evidence"
DEFAULT_TOOL = "synthetic-stub"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def input_fingerprint(
    founder_id: str, objective: str, new_task_token: str = ""
) -> str:
    payload = {
        "fixture": SYNTHETIC_FIXTURE_ID,
        "founder_id": founder_id.strip(),
        "new_task_token": (new_task_token or "").strip(),
        "objective": " ".join(objective.split()),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def method_fingerprint(method: str, hypothesis: str, tool_path: str) -> str:
    raw = json.dumps(
        {"hypothesis": hypothesis, "method": method, "tool_path": tool_path},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assert_authorised(founder_id: str, authorised: Iterable[str]) -> str:
    ident = founder_id.strip()
    if not ident:
        raise PermissionError("founder_id required")
    if ident not in set(authorised):
        raise PermissionError("founder not authorised for synthetic pilot")
    return ident


def assert_bounded_objective(objective: str) -> str:
    text = objective.strip()
    if not text:
        raise ValueError("objective required")
    if len(text) > MAX_OBJECTIVE_CHARS:
        raise ValueError("objective exceeds synthetic bound")
    if SYNTHETIC_MARKER not in text:
        raise ValueError("objective must be labelled [SYNTHETIC]")
    return " ".join(text.split())


def _new_task(ident: str, text: str, fingerprint: str) -> TaskContract:
    return TaskContract(
        task_id=f"nx1-{fingerprint[:12]}",
        founder_id=ident,
        objective=text,
        input_fingerprint=fingerprint,
        revision=1,
        created_at=utc_now(),
    )


def accept_or_resume(
    store: SyntheticStore,
    *,
    founder_id: str,
    objective: str,
    resume_task_id: str | None = None,
    new_task_token: str = "",
    authorised: Iterable[str] = DEFAULT_AUTHORISED,
) -> tuple[TaskContract, bool, bool]:
    """Return (contract, duplicate, resumed). Never forks on replay."""
    ident = assert_authorised(founder_id, authorised)
    if resume_task_id:
        existing = store.get_task(resume_task_id)
        if existing is None:
            raise KeyError(f"unknown task: {resume_task_id}")
        return existing, False, True
    text = assert_bounded_objective(objective)
    fingerprint = input_fingerprint(ident, text, new_task_token)
    found = store.get_by_fingerprint(fingerprint)
    if found is not None:
        return found, True, False
    task = _new_task(ident, text, fingerprint)
    store.put_task(task)
    return task, False, False


def _attempt(
    fingerprint: str,
    method: str,
    hypothesis: str,
    tool_path: str,
    outcome: str,
) -> MethodAttempt:
    return MethodAttempt(
        fingerprint=fingerprint,
        method=method,
        hypothesis=hypothesis,
        tool_path=tool_path,
        outcome=outcome,  # type: ignore[arg-type]
    )


def run_method(
    store: SyntheticStore,
    task: TaskContract,
    *,
    method: str,
    hypothesis: str,
    tool_path: str = DEFAULT_TOOL,
    inject_failure: bool = False,
) -> MethodAttempt:
    fingerprint = method_fingerprint(method, hypothesis, tool_path)
    if fingerprint in store.failed_fingerprints(task.task_id):
        attempt = _attempt(fingerprint, method, hypothesis, tool_path, "rejected_duplicate")
        store.record_attempt(task.task_id, attempt)
        return attempt
    outcome = "failed" if inject_failure else "passed"
    attempt = _attempt(fingerprint, method, hypothesis, tool_path, outcome)
    store.record_attempt(task.task_id, attempt)
    return attempt


def evidence_for(task: TaskContract, attempt: MethodAttempt) -> tuple[str, ...]:
    if attempt.outcome != "passed":
        return ()
    return (
        f"synthetic:task:{task.task_id}",
        f"synthetic:method:{attempt.fingerprint[:12]}",
        f"synthetic:fixture:{SYNTHETIC_FIXTURE_ID}",
    )
