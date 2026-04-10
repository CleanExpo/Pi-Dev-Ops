"""
orchestrator.py — Multi-session fan-out parallelism (RA-464).

Implements the P3-B fan-out pattern:
  Orchestrator decomposes a complex brief into N independent sub-tasks,
  launches N parallel worker sessions via asyncio.gather(), then waits
  for all to complete.

Usage:
  POST /api/build/parallel  { repo_url, brief, n_workers, model, intent }
"""
import json
import os
import time
import uuid

from . import config
from .sessions import create_session, em, run_cmd, BuildSession, _sessions
from .brief import classify_intent
from .sessions import _select_model


async def _decompose_brief(brief: str, n_workers: int, repo_url: str, workspace: str) -> list[str]:
    """Call claude -p to split a brief into n_workers independent sub-tasks.
    Returns a list of sub-brief strings. Falls back to [brief] * n on failure."""
    decompose_prompt = (
        f"You are a task decomposer. Split the following brief into exactly {n_workers} "
        f"independent sub-tasks that can be worked on in parallel without conflicts.\n\n"
        f"Brief: {brief}\n\n"
        f"Repo: {repo_url}\n\n"
        f"Rules:\n"
        f"- Each sub-task must be self-contained and not depend on another sub-task's output\n"
        f"- Each sub-task must be a complete, actionable brief\n"
        f"- Output ONLY a JSON array of {n_workers} strings, no other text\n"
        f"- Example: [\"Sub-task 1: ...\", \"Sub-task 2: ...\"]"
    )
    try:
        rc, out, _ = await run_cmd(
            workspace, config.CLAUDE_CMD, "-p", decompose_prompt,
            "--model", _select_model("planner"), "--output-format", "text",
            timeout=60
        )
        if rc == 0 and out.strip():
            start = out.find("[")
            end = out.rfind("]") + 1
            if start >= 0 and end > start:
                sub_briefs = json.loads(out[start:end])
                if isinstance(sub_briefs, list) and sub_briefs:
                    return [str(s) for s in sub_briefs[:n_workers]]
    except Exception:
        pass
    return [brief] * n_workers


async def fan_out(
    repo_url: str,
    brief: str,
    n_workers: int = 2,
    model: str = "sonnet",
    intent: str = "",
    evaluator_enabled: bool = True,
) -> dict:
    """Fan-out a brief into N parallel worker sessions.

    Returns:
        {
            "parent_id": str,
            "worker_ids": [str, ...],
            "n_workers": int,
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
        return {"parent_id": parent_id, "worker_ids": [], "n_workers": 0, "status": "failed"}

    # Decompose brief
    em(parent, "phase", f"  Decomposing into {n_workers} sub-tasks...")
    sub_briefs = await _decompose_brief(brief, n_workers, repo_url, shared_ws)
    for i, sb in enumerate(sub_briefs):
        em(parent, "system", f"  [{i+1}] {sb[:100]}")

    # Launch N worker sessions with tier escalation on failure
    worker_ids = []
    escalated = []
    for i, sub_brief in enumerate(sub_briefs):
        try:
            s = await create_session(
                repo_url=repo_url,
                brief=sub_brief,
                model=model,
                evaluator_enabled=evaluator_enabled,
                intent=resolved_intent,
                parent_session_id=parent_id,
            )
            worker_ids.append(s.id)
            em(parent, "system", f"  Launched worker {i+1}: {s.id}")
        except RuntimeError as e:
            em(parent, "error", f"  Worker {i+1} launch failed ({e}) — escalating to opus")
            # Tier escalation: retry failed worker with opus (one-shot)
            opus_model = _select_model("planner")  # planner tier = opus
            try:
                s2 = await create_session(
                    repo_url=repo_url,
                    brief=sub_brief,
                    model=opus_model,
                    evaluator_enabled=evaluator_enabled,
                    intent=resolved_intent,
                    parent_session_id=parent_id,
                )
                worker_ids.append(s2.id)
                escalated.append(s2.id)
                em(parent, "system", f"  Escalated worker {i+1} (opus): {s2.id}")
            except RuntimeError as e2:
                em(parent, "error", f"  Escalated worker {i+1} also failed: {e2}")

    succeeded = len(worker_ids) > 0
    parent.status = "complete" if succeeded else "failed"
    em(parent, "success" if succeeded else "error",
       f"  {'All workers launched' if succeeded else 'No workers started'}"
       + (f" ({len(escalated)} escalated to opus)" if escalated else ""))

    return {
        "parent_id": parent_id,
        "worker_ids": worker_ids,
        "n_workers": len(worker_ids),
        "escalated_ids": escalated,
        "status": "launched" if succeeded else "failed",
    }
