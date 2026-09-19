"""Background parent execution and dependency-wave bookkeeping."""
import asyncio
import logging
import os
from . import config, persistence
from .git_auth import GitAuthError
from .session_model import BuildSession, em
_log = logging.getLogger("pi-ceo.orchestrator")

async def clone_parent(parent, run_cmd, clone_env_factory):
    parent_id, repo_url = parent.id, parent.repo_url
    shared_ws = os.path.join(config.WORKSPACE_ROOT, f"{parent_id}-shared")
    os.makedirs(shared_ws, exist_ok=True)
    em(parent, "phase", "  Cloning for decomposition...")
    try:
        clone_env = clone_env_factory(repo_url)
    except GitAuthError as exc:
        em(parent, "error", f"  Clone blocked: {exc.reason}")
        parent.status = "failed"
        parent.error = exc.reason
        return None
    rc, _, stderr = await run_cmd(
        shared_ws, "git", "clone", "--depth", "1", repo_url, shared_ws,
        timeout=60, env=clone_env,
    )
    if rc != 0:
        em(parent, "error", f"  Clone failed: {stderr[:200]}")
        parent.status = "failed"
        parent.error = f"Clone failed: {stderr[:200]}"
        return None

    return shared_ws


def dependency_waves(parent, decomposed, topological_sort):
    # Build topological waves
    if decomposed and isinstance(decomposed[0], dict):
        waves = topological_sort(decomposed)
        em(parent, "system", f"  {len(decomposed)} tasks in {len(waves)} wave(s)")
        for i, wave in enumerate(waves, 1):
            titles = ", ".join(t.get("title", str(t.get("id", "?"))) for t in wave)
            em(parent, "system", f"  Wave {i}: [{titles}]")
    else:
        # Fallback: plain strings — treat as single wave, log truncated briefs
        waves = [decomposed]  # type: ignore[list-item]
        for i, sb in enumerate(decomposed):
            em(parent, "system", f"  [{i+1}] {str(sb)[:100]}")

    return waves


async def _run_fan_out(
    parent: BuildSession,
    brief: str,
    n_workers: int,
    model: str,
    resolved_intent: str,
    evaluator_enabled: bool,
    *, run_cmd, decompose, topological_sort, launch_wave, wait_for_wave, clone_env_factory,
) -> None:
    """Run dependency waves and only complete after every required worker passes."""
    repo_url = parent.repo_url

    shared_ws = await clone_parent(parent, run_cmd, clone_env_factory)
    if shared_ws is None:
        return

    # Decompose brief — RA-1030: returns list[dict] or list[str] (fallback)
    em(parent, "phase", f"  Decomposing into {n_workers} sub-tasks...")
    decomposed = await decompose(brief, n_workers, repo_url, shared_ws)

    waves = dependency_waves(parent, decomposed, topological_sort)

    await run_waves(parent, waves, model, evaluator_enabled, resolved_intent, shared_ws,
                    launch_wave, wait_for_wave)


async def run_waves(parent, waves, model, evaluator_enabled, resolved_intent, shared_ws,
                    launch_wave, wait_for_wave):
    parent_id, repo_url = parent.id, parent.repo_url
    # Launch waves sequentially; within each wave all workers fire in parallel
    all_escalated: list[str] = []

    succeeded = bool(waves)
    for wave_num, wave in enumerate(waves, 1):
        em(parent, "phase", f"  Launching wave {wave_num} ({len(wave)} task(s))...")
        w_ids, w_esc = await launch_wave(
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
        all_escalated.extend(w_esc)
        wave_passed = await wait_for_wave(w_ids, parent, wave_num)
        if len(w_ids) != len(wave) or not wave_passed:
            succeeded = False
            em(parent, "error", f"  Wave {wave_num} failed; dependent tasks were not launched")
            break

    parent.status = "complete" if succeeded else "failed"
    em(parent, "success" if succeeded else "error",
       f"  {'All required workers completed' if succeeded else 'Required work did not complete'}"
       + (f" ({len(all_escalated)} retried)" if all_escalated else ""))


async def _stop_children(parent, sessions_map):
    """Drain only this parent's active workers on every exceptional exit."""
    from .sessions import kill_session
    terminal = {"complete", "failed", "killed", "interrupted", "error", "stalled", "blocked"}
    children = [
        child for child in list(sessions_map.values())
        if getattr(child, "parent_session_id", None) == parent.id
        and child.status not in terminal
    ]
    stopped = await asyncio.gather(
        *(kill_session(child.id) for child in children), return_exceptions=True
    )
    if any(result is not True for result in stopped):
        parent.status = "failed"
        reason = "Orchestration stopped, but some workers could not be stopped"
        parent.error = f"{parent.error}; {reason}" if parent.error else reason


async def run_parent(parent, brief, n_workers, model, resolved_intent, evaluator_enabled, run_fan_out, sessions_map):
    try:
        await run_fan_out(parent, brief, n_workers, model, resolved_intent, evaluator_enabled)
    except asyncio.CancelledError:
        if parent.status != "killed":
            parent.status = "interrupted"
        await _stop_children(parent, sessions_map)
        em(parent, "error", "  Orchestration stopped before completion")
        raise
    except Exception as exc:
        parent.status = "failed"
        parent.error = str(exc)
        em(parent, "error", f"  Orchestration failed: {exc}")
        _log.exception("Fan-out failed for %s", parent.id)
        await _stop_children(parent, sessions_map)
    finally:
        persistence.save_session(parent)
