"""
orchestrator.py — Multi-session fan-out parallelism (RA-464).

Implements the P3-B fan-out pattern:
  Orchestrator decomposes a complex brief into N independent sub-tasks,
  launches N parallel worker sessions via asyncio.gather(), then waits
  for all to complete.

RA-1030: Decomposition now returns a dependency graph with test scenarios.
  Workers are launched in topological waves — tasks with no unmet dependencies
  fire first; later waves wait for prior waves to complete.

Usage:
  POST /api/build/parallel  { repo_url, brief, n_workers, model, intent }
"""
import asyncio
import json
import logging
import os
import time
import uuid

from . import config
from .sessions import create_session, em, run_cmd, BuildSession, _sessions, _run_claude_via_sdk
from .brief import classify_intent
from .sessions import _select_model

_log = logging.getLogger("pi-ceo.orchestrator")


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

    # SDK path — try first when TAO_USE_AGENT_SDK=1
    if config.USE_AGENT_SDK:
        try:
            rc, out, _ = await _run_claude_via_sdk(
                decompose_prompt, model=_select_model("planner"),
                workspace=workspace, timeout=90,
                session_id="", phase="orchestrator.decompose",
            )
            if rc == 0 and out.strip():
                parsed = _parse_tasks(out)
                if parsed:
                    _log.info("Decomposed into %d tasks via SDK", len(parsed))
                    return parsed
        except Exception:
            pass  # fall through to subprocess

    # Subprocess fallback
    try:
        rc, out, _ = await run_cmd(
            workspace, config.CLAUDE_CMD, *config.CLAUDE_EXTRA_FLAGS, "-p", decompose_prompt,
            "--model", _select_model("planner"), "--output-format", "text",
            timeout=90
        )
        if rc == 0 and out.strip():
            parsed = _parse_tasks(out)
            if parsed:
                _log.info("Decomposed into %d tasks via subprocess", len(parsed))
                return parsed
    except Exception:
        pass

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
            em(parent, "error", f"  Wave {wave_num} — {label} failed ({e}) — escalating to opus")
            opus_model = _select_model("planner")
            try:
                s2 = await create_session(
                    repo_url=repo_url,
                    brief=sub_brief,
                    model=opus_model,
                    evaluator_enabled=evaluator_enabled,
                    intent=resolved_intent,
                    parent_session_id=parent_id,
                    shared_workspace=shared_ws,  # RA-1029: worker uses worktree from shared clone
                )
                worker_ids.append(s2.id)
                escalated.append(s2.id)
                em(parent, "system", f"  Wave {wave_num} — escalated {label} (opus): {s2.id}")
            except RuntimeError as e2:
                em(parent, "error", f"  Wave {wave_num} — escalated {label} also failed: {e2}")

    return worker_ids, escalated


async def _wait_for_wave(session_ids: list[str], parent: BuildSession, wave_num: int) -> None:
    """Poll until all sessions in a wave reach a terminal state."""
    from .session_model import _sessions as _sess_store  # noqa: PLC0415
    terminal = {"complete", "failed", "killed", "interrupted", "error"}
    poll_interval = 5  # seconds
    em(parent, "phase", f"  Waiting for wave {wave_num} ({len(session_ids)} workers) to finish...")
    while True:
        states = {sid: _sess_store.get(sid) for sid in session_ids}
        done = all(
            (s is None or (hasattr(s, "status") and s.status in terminal))
            for s in states.values()
        )
        if done:
            break
        await asyncio.sleep(poll_interval)
    em(parent, "system", f"  Wave {wave_num} complete.")


async def fan_out(
    repo_url: str,
    brief: str,
    n_workers: int = 2,
    model: str = "sonnet",
    intent: str = "",
    evaluator_enabled: bool = True,
) -> dict:
    """Fan-out a brief into N parallel worker sessions, launched in dependency order.

    RA-1030: Decomposition returns a dependency graph. Tasks are sorted into
    topological waves — wave 1 fires immediately; subsequent waves wait for
    the prior wave to reach a terminal state before launching.

    Returns:
        {
            "parent_id": str,
            "worker_ids": [str, ...],
            "n_workers": int,
            "waves": int,
            "escalated_ids": [str, ...],
            "status": "launched" | "failed"
        }
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

    # Clone repo once for decomposition
    shared_ws = os.path.join(config.WORKSPACE_ROOT, f"{parent_id}-shared")
    os.makedirs(shared_ws, exist_ok=True)
    em(parent, "phase", "  Cloning for decomposition...")
    rc, _, stderr = await run_cmd(
        shared_ws, "git", "clone", "--depth", "1", repo_url, shared_ws, timeout=60
    )
    if rc != 0:
        em(parent, "error", f"  Clone failed: {stderr[:200]}")
        parent.status = "failed"
        return {"parent_id": parent_id, "worker_ids": [], "n_workers": 0, "waves": 0, "status": "failed"}

    # Decompose brief — RA-1030: returns list[dict] or list[str] (fallback)
    em(parent, "phase", f"  Decomposing into {n_workers} sub-tasks...")
    decomposed = await _decompose_brief(brief, n_workers, repo_url, shared_ws)

    # Build topological waves
    if decomposed and isinstance(decomposed[0], dict):
        waves = _topological_sort(decomposed)
        em(parent, "system", f"  {len(decomposed)} tasks in {len(waves)} wave(s)")
        for i, wave in enumerate(waves, 1):
            titles = ", ".join(t.get("title", str(t.get("id", "?"))) for t in wave)
            em(parent, "system", f"  Wave {i}: [{titles}]")
    else:
        # Fallback: plain strings — treat as single wave, log truncated briefs
        waves = [decomposed]  # type: ignore[list-item]
        for i, sb in enumerate(decomposed):
            em(parent, "system", f"  [{i+1}] {str(sb)[:100]}")

    # Launch waves sequentially; within each wave all workers fire in parallel
    all_worker_ids: list[str] = []
    all_escalated: list[str] = []

    for wave_num, wave in enumerate(waves, 1):
        if wave_num > 1:
            # Wait for previous wave's workers before launching this one
            prev_wave_ids = all_worker_ids[-(len(waves[wave_num - 2])):]  # workers from prior wave
            await _wait_for_wave(prev_wave_ids, parent, wave_num - 1)

        em(parent, "phase", f"  Launching wave {wave_num} ({len(wave)} task(s))...")
        w_ids, w_esc = await _launch_wave(
            wave,
            wave_num,
            repo_url=repo_url,
            model=model,
            evaluator_enabled=evaluator_enabled,
            resolved_intent=resolved_intent,
            parent_id=parent_id,
            shared_ws=shared_ws,
            parent=parent,
        )
        all_worker_ids.extend(w_ids)
        all_escalated.extend(w_esc)

    succeeded = len(all_worker_ids) > 0
    parent.status = "complete" if succeeded else "failed"
    em(parent, "success" if succeeded else "error",
       f"  {'All workers launched' if succeeded else 'No workers started'}"
       + (f" ({len(all_escalated)} escalated to opus)" if all_escalated else ""))

    return {
        "parent_id": parent_id,
        "worker_ids": all_worker_ids,
        "n_workers": len(all_worker_ids),
        "waves": len(waves),
        "escalated_ids": all_escalated,
        "status": "launched" if succeeded else "failed",
    }
