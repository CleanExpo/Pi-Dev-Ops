"""orchestrator.py — Multi-session fan-out (RA-464, RA-1030).

POST /api/build/parallel  { repo_url, brief, n_workers, model, intent }
"""
from . import orchestration_run
from .git_auth import git_auth_env
import asyncio
import json
import logging
import time
import uuid

from . import config, persistence
from .sessions import create_session, em, run_cmd, BuildSession, _sessions, _run_claude_via_sdk
from .brief import classify_intent
from .model_policy import select_model  # RA-1099: hardwired model routing policy

_log = logging.getLogger("pi-ceo.orchestrator")
_fan_out_tasks: dict[str, asyncio.Task] = {}


async def cancel_fan_out(sid: str) -> bool | None:
    """Stop a parent through the same kill endpoint used by ordinary sessions."""
    task = _fan_out_tasks.get(sid)
    if task is None or task.done():
        return None
    parent = _sessions[sid]
    parent.status = "killed"
    if not task.cancelling():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    # Cancellation before the first event-loop turn skips the runner's finally.
    persistence.save_session(parent)
    return parent.status == "killed"


# ── RA-1030: Dependency-graph decomposition ───────────────────────────────────

def _topological_sort(tasks: list[dict]) -> list[list[dict]]:
    """Group tasks into execution waves based on depends_on. Returns list of waves."""
    waves = []
    remaining = {t["id"]: t for t in tasks}
    completed: set = set()
    while remaining:
        wave = [t for t in remaining.values() if all(d in completed for d in t.get("depends_on", []))]
        if not wave:  # circular dependency or error — put everything left in one wave
            wave = list(remaining.values())
        for t in wave:
            completed.add(t["id"])
            del remaining[t["id"]]
        waves.append(wave)
    return waves


def _task_brief(task: dict) -> str:
    """Build the full brief string for a worker task, injecting test scenarios."""
    brief = task.get("brief", task.get("title", ""))
    scenarios = task.get("test_scenarios", [])
    if scenarios:
        brief += "\n\n## Expected test scenarios\n" + "\n".join(f"- {s}" for s in scenarios)
    return brief


async def _decompose_brief(
    brief: str, n_workers: int, repo_url: str, workspace: str
) -> list[dict] | list[str]:
    """Call claude -p to split a brief into n_workers sub-tasks with dependency graph.

    Returns:
        list[dict]  — RA-1030 rich format: [{id, title, brief, depends_on, test_scenarios, is_behavioral}]
        list[str]   — fallback: plain sub-brief strings (backward compatible)
    """
    decompose_prompt = (
        f"You are a task decomposer. Split the following brief into between 3 and 8 "
        f"sub-tasks (aim for {n_workers}) that together implement the full brief.\n\n"
        f"Brief: {brief}\n\n"
        f"Repo: {repo_url}\n\n"
        f"Rules:\n"
        f"- Each sub-task must be a complete, actionable brief\n"
        f"- Use depends_on to express real dependencies (IDs of tasks that must finish first)\n"
        f"- Independent tasks should have empty depends_on so they can run in parallel\n"
        f"- For each task, include 2-4 test_scenarios (at least one happy path, one edge case)\n"
        f"- Set is_behavioral=true for tasks that change user-visible behaviour\n"
        f"- Output ONLY a JSON array, no markdown fences, no other text\n"
        f"- Schema: "
        f'[{{"id": 1, "title": "...", "brief": "...", "depends_on": [], '
        f'"test_scenarios": ["happy path: ...", "edge case: ..."], "is_behavioral": true}}]'
    )

    def _parse_tasks(out: str) -> list[dict] | None:
        # Strip markdown code fences if present
        stripped = out.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()
        start = stripped.find("[")
        end = stripped.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                tasks = json.loads(stripped[start:end])
                if isinstance(tasks, list) and tasks:
                    # Validate each entry has required keys; coerce id to int
                    valid = []
                    for t in tasks:
                        if isinstance(t, dict) and "brief" in t:
                            t.setdefault("id", len(valid) + 1)
                            t["id"] = int(t["id"])
                            t.setdefault("title", f"Task {t['id']}")
                            t.setdefault("depends_on", [])
                            t.setdefault("test_scenarios", [])
                            t.setdefault("is_behavioral", False)
                            valid.append(t)
                    if valid:
                        return valid
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # SDK-only path (RA-1094B). Subprocess fallback removed — SDK is mandatory.
    # RA-1099: Decomposition is the Senior Orchestrator's job → opus per policy.
    try:
        rc, out, _ = await _run_claude_via_sdk(
            decompose_prompt, model=select_model("orchestrator"),
            workspace=workspace, timeout=90,
            session_id="", phase="orchestrator.decompose",
        )
        if rc == 0 and out.strip():
            parsed = _parse_tasks(out)
            if parsed:
                _log.info("Decomposed into %d tasks via SDK", len(parsed))
                return parsed
    except Exception as exc:
        _log.warning("SDK decomposition failed: %s", exc)

    # Final fallback — plain strings, backward compatible
    _log.warning("Decomposition failed; falling back to %d copies of brief", n_workers)
    return [brief] * n_workers


async def _launch_wave(
    wave: list[dict] | list[str],
    wave_num: int,
    *,
    repo_url: str,
    model: str,
    evaluator_enabled: bool,
    resolved_intent: str,
    parent_id: str,
    shared_ws: str,
    parent: BuildSession,
) -> tuple[list[str], list[str]]:
    """Launch all tasks in a single wave, returning (worker_ids, escalated_ids)."""
    worker_ids: list[str] = []
    escalated: list[str] = []

    for i, task in enumerate(wave):
        # Support both rich-dict tasks (RA-1030) and plain-string fallback
        if isinstance(task, dict):
            sub_brief = _task_brief(task)
            label = task.get("title", f"task {task.get('id', i+1)}")
        else:
            sub_brief = task
            label = f"task {i+1}"

        try:
            s = await create_session(
                repo_url=repo_url,
                brief=sub_brief,
                model=model,
                evaluator_enabled=evaluator_enabled,
                intent=resolved_intent,
                parent_session_id=parent_id,
                shared_workspace=shared_ws,  # RA-1029: worker uses worktree from shared clone
            )
            worker_ids.append(s.id)
            em(parent, "system", f"  Wave {wave_num} — launched {label}: {s.id}")
        except RuntimeError as e:
            # RA-1099: workers are 'generator' role — opus is policy-blocked here.
            # Retry once with the configured generator model (sonnet by default).
            retry_model = select_model("generator")
            em(parent, "error",
               f"  Wave {wave_num} — {label} failed ({e}) — retrying with {retry_model} "
               f"(opus policy-blocked for non-PM/orchestrator roles)")
            try:
                s2 = await create_session(
                    repo_url=repo_url,
                    brief=sub_brief,
                    model=retry_model,
                    evaluator_enabled=evaluator_enabled,
                    intent=resolved_intent,
                    parent_session_id=parent_id,
                    shared_workspace=shared_ws,  # RA-1029: worker uses worktree from shared clone
                )
                worker_ids.append(s2.id)
                escalated.append(s2.id)
                em(parent, "system", f"  Wave {wave_num} — retried {label} ({retry_model}): {s2.id}")
            except RuntimeError as e2:
                em(parent, "error", f"  Wave {wave_num} — retry {label} also failed: {e2}")

    return worker_ids, escalated


async def _wait_for_wave(session_ids: list[str], parent: BuildSession, wave_num: int) -> bool:
    """Poll until all sessions in a wave reach a terminal state.

    RA-1966 — TAO kill-switch: every poll checks TAO_HARD_STOP_FILE so an
    operator can abort an in-flight wave without restarting the server.
    """
    from .session_model import _sessions as _sess_store  # noqa: PLC0415
    from . import kill_switch as _ks                       # noqa: PLC0415
    terminal = {"complete", "failed", "killed", "interrupted", "error", "stalled", "blocked"}
    poll_interval = 5  # seconds
    em(parent, "phase", f"  Waiting for wave {wave_num} ({len(session_ids)} workers) to finish...")
    counter = _ks.LoopCounter()
    while True:
        try:
            counter.tick()
        except _ks.KillSwitchAbort as abort:
            em(parent, "error",
               f"  Wave {wave_num} aborted by TAO kill-switch: {abort.reason} {abort.snapshot}")
            raise
        states = {sid: _sess_store.get(sid) for sid in session_ids}
        done = all(
            (s is None or (hasattr(s, "status") and s.status in terminal))
            for s in states.values()
        )
        if done:
            break
        await asyncio.sleep(poll_interval)
    em(parent, "system", f"  Wave {wave_num} complete.")
    return bool(states) and all(s is not None and s.status == "complete" for s in states.values())


async def fan_out(
    repo_url: str,
    brief: str,
    n_workers: int = 2,
    model: str = "sonnet",
    intent: str = "",
    evaluator_enabled: bool = True,
) -> dict:
    """Persist a parent and return its receipt before running background work.

    Decomposition and workers may take minutes. The launch receipt therefore
    contains no worker IDs yet; poll sessions with this parent ID for children
    and the parent's eventual terminal outcome.
    """
    n_workers = max(1, min(n_workers, config.MAX_CONCURRENT_SESSIONS))
    resolved_intent = intent or classify_intent(brief)

    # Create a lightweight parent session to track the group
    parent_id = uuid.uuid4().hex[:12]
    parent = BuildSession(
        id=parent_id,
        repo_url=repo_url,
        started_at=time.time(),
        status="orchestrating",
        evaluator_enabled=False,
    )
    _sessions[parent_id] = parent
    em(parent, "phase", "  Pi CEO Fan-Out Orchestrator")
    em(parent, "system", f"  Parent:  {parent_id}")
    em(parent, "system", f"  Workers: {n_workers}")
    em(parent, "system", f"  Intent:  {resolved_intent.upper()}")
    persistence.save_session(parent)

    # Keep a strong reference until completion, as for background scans.
    task = asyncio.create_task(orchestration_run.run_parent(
        parent, brief, n_workers, model, resolved_intent, evaluator_enabled, _run_fan_out, _sessions,
    ))
    _fan_out_tasks[parent_id] = task
    task.add_done_callback(lambda _: _fan_out_tasks.pop(parent_id, None))
    return {
        "parent_id": parent_id,
        "worker_ids": [],
        "n_workers": 0,
        "waves": 0,
        "escalated_ids": [],
        "status": "launched",
    }


async def _run_fan_out(parent, brief, n_workers, model, resolved_intent, evaluator_enabled):
    return await orchestration_run._run_fan_out(
        parent, brief, n_workers, model, resolved_intent, evaluator_enabled,
        run_cmd=run_cmd, decompose=_decompose_brief, topological_sort=_topological_sort,
        launch_wave=_launch_wave, wait_for_wave=_wait_for_wave, clone_env_factory=git_auth_env,
    )
