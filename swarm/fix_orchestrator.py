"""swarm/fix_orchestrator.py — routes WorkOrders to specialist Claude Code
agents, manages the fix lifecycle: diagnose → fix → PR → sandbox → Board.

Reads open [WorkOrder] Linear tickets, spawns the appropriate specialist
agent (via Claude Code SDK / Pi-CEO session), tracks progress, and routes
completed fixes to the Board production gate.

Public API:
    run_cycle(repo_root) -> OrchestratorResult
    should_run(state)    -> bool
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.fix_orchestrator")

STATE_KEY = "last_fix_orchestrator"
MAX_ACTIVE_FIXES = 3   # concurrent specialist agents cap

# Specialist → skill allowlist (what tools each agent may use)
SPECIALIST_SKILLS: dict[str, list[str]] = {
    "IDD-1": ["read", "grep", "diff", "comment_pr"],
    "IDD-3": ["read", "edit", "write", "bash_python", "create_pr"],
    "IDD-4": ["read", "edit", "write", "bash_node", "create_pr"],
    "IDD-5": ["read", "edit", "write", "bash_infra", "vercel_cli", "create_pr"],
    "SD-1":  ["read", "edit", "write", "bash_sql", "create_pr"],
    "SD-2":  ["read", "grep", "audit", "create_pr"],
    "SD-3":  ["read", "edit", "write", "bash_node", "create_pr"],
    "SD-4":  ["read", "edit", "write", "xcode_cli", "create_pr"],
}

# Specialist system prompts — domain expertise each agent carries
SPECIALIST_PROMPTS: dict[str, str] = {
    "IDD-1": (
        "You are IDD-1, the Pi Reviewer — a senior code review agent with Opus 4.7 depth. "
        "Your job: review PRs across the Unite-Group portfolio as if you are the founder. "
        "Be direct, specific, and actionable. Surface architecture concerns, security issues, "
        "and anything that would embarrass the team in production. Never approve just to be nice."
    ),
    "IDD-3": (
        "You are IDD-3, a senior Python/FastAPI engineer with 15+ years experience. "
        "You own Pi-CEO swarm (Python), CCW-CRM backend (FastAPI), and all Python services. "
        "Fix the assigned issue surgically — minimum code change that solves the problem. "
        "Never introduce new dependencies without justification. Always add tests."
    ),
    "IDD-4": (
        "You are IDD-4, a senior TypeScript/Next.js engineer with 15+ years experience. "
        "You own all Next.js frontends across the portfolio: CCW-CRM, RestoreAssist web, "
        "Synthex, NRPG, DR. Fix the assigned issue with surgical precision. "
        "Follow existing patterns. No gratuitous refactoring. Tests required."
    ),
    "IDD-5": (
        "You are IDD-5, a senior infrastructure and DevOps engineer. "
        "You own Railway, Vercel, Supabase, GitHub Actions across all 11 projects. "
        "Fix build failures, deployment issues, CI configuration, and environment problems. "
        "Document every env var change. Never touch production without sandbox validation."
    ),
    "SD-1": (
        "You are SD-1, a senior database architect with deep Supabase/Postgres expertise. "
        "Fix schema drift, migration issues, RLS policies, and query performance. "
        "Every migration must be reversible. Test in sandbox first."
    ),
    "SD-2": (
        "You are SD-2, a senior security specialist. "
        "Fix vulnerabilities, dependency advisories, auth issues, and secret exposure. "
        "Every fix is a potential audit finding — document the issue and resolution clearly."
    ),
    "SD-3": (
        "You are SD-3, a senior API design specialist. "
        "Fix endpoint errors, webhook failures, SDK issues, and integration problems. "
        "Maintain backwards compatibility unless a breaking change is explicitly approved."
    ),
    "SD-4": (
        "You are SD-4, a senior mobile platform specialist. "
        "You own RestoreAssist iOS — App Store pipeline, TestFlight, Swift/React Native. "
        "Fix App Store rejections, build failures, and crash reports with precision."
    ),
}


@dataclass
class FixJob:
    job_id: str
    work_order_id: str
    project_id: str
    failure_type: str
    severity: str
    description: str
    specialist: str
    linear_ticket_id: str
    status: str = "dispatched"   # dispatched | fixing | pr_created | board_pending | done | failed
    pr_url: str = ""
    sandbox_url: str = ""
    board_session_id: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OrchestratorResult:
    jobs_dispatched: list[str] = field(default_factory=list)
    jobs_completed: list[str] = field(default_factory=list)
    jobs_failed: list[str] = field(default_factory=list)
    board_sessions_queued: list[str] = field(default_factory=list)
    error: str | None = None


def should_run(state: dict) -> bool:
    """Run every cycle — fix orchestrator checks for new work orders each cycle."""
    return True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _jobs_log() -> Path:
    p = _repo_root() / ".harness" / "swarm" / "fix_jobs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_active_jobs() -> list[FixJob]:
    log_path = _jobs_log()
    if not log_path.exists():
        return []
    jobs: dict[str, FixJob] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            job = FixJob(**{k: v for k, v in row.items()
                            if k in FixJob.__dataclass_fields__})
            jobs[job.job_id] = job
        except Exception:  # noqa: BLE001
            continue
    return [j for j in jobs.values()
            if j.status not in ("done", "failed")]


def _save_job(job: FixJob) -> None:
    job.updated_at = datetime.now(timezone.utc).isoformat()
    with _jobs_log().open("a", encoding="utf-8") as f:
        f.write(json.dumps(job.__dict__) + "\n")


def _fetch_open_work_orders() -> list[dict[str, Any]]:
    """Fetch open [WorkOrder] tickets from Linear."""
    try:
        from .margot_tools import _linear_gql  # noqa: PLC0415
        res = _linear_gql(
            """query {
                issues(filter: {
                    title: {startsWith: "[WorkOrder]"},
                    state: {type: {in: ["backlog","unstarted"]}}
                }, first: 20) {
                    nodes {
                        id identifier title description
                        priority createdAt
                    }
                }
            }"""
        )
        return (res.get("data") or {}).get("issues", {}).get("nodes", []) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("fix_orchestrator: Linear fetch failed (%s)", exc)
        return []


def _ollama_triage(user_message: str, system: str = "You are a precise engineering triage agent. Be concise.") -> str:
    """Use Gemma 4 via Ollama for zero-cost triage and routing decisions."""
    try:
        from . import ollama_client, config  # noqa: PLC0415
        result = ollama_client.chat(
            model=config.OLLAMA_TRIAGE_MODEL,
            system=system,
            user_message=user_message,
            temperature=0.1,
        )
        return result or ""
    except Exception as exc:  # noqa: BLE001
        log.debug("fix_orchestrator: ollama triage unavailable (%s)", exc)
        return ""


def _parse_work_order_from_ticket(ticket: dict[str, Any]) -> dict[str, Any] | None:
    """Extract structured work order fields from the Linear ticket description.

    Uses regex for the structured title (zero cost), Gemma 4 via Ollama only
    for ambiguous cases that need LLM interpretation.
    """
    desc = ticket.get("description", "")
    title = ticket.get("title", "")

    # Primary: structured title parse — zero cost
    import re  # noqa: PLC0415
    m = re.search(r'\[WorkOrder\]\s+([a-z-]+)\s+[—-]\s+([a-z_]+)\s+\((\w+)\)',
                  title)
    if not m:
        return None

    project_id = m.group(1)
    failure_type = m.group(2)
    severity = m.group(3)

    # Use Gemma 4 to refine specialist assignment for ambiguous failure types
    specialist = _guess_specialist(failure_type, project_id)
    if failure_type == "unknown" or failure_type.startswith("dora_"):
        triage_prompt = (
            f"You are a software engineering triage agent. "
            f"Given this issue, reply with ONLY the specialist code "
            f"(one of: IDD-1, IDD-3, IDD-4, IDD-5, SD-1, SD-2, SD-3, SD-4).\n\n"
            f"Project: {project_id}\n"
            f"Issue: {desc[:300]}\n\n"
            f"Specialist code:"
        )
        ollama_resp = _ollama_triage(triage_prompt).strip().upper()
        if ollama_resp in SPECIALIST_SKILLS:
            specialist = ollama_resp

    return {
        "linear_ticket_id": ticket.get("identifier", ""),
        "linear_issue_id": ticket.get("id", ""),
        "project_id": project_id,
        "failure_type": failure_type,
        "severity": severity,
        "description": desc,
        "specialist": specialist,
    }


def _guess_specialist(failure_type: str, project_id: str) -> str:
    from .project_health_monitor import _assign_specialist  # noqa: PLC0415
    return _assign_specialist(failure_type, project_id)


def _build_fix_prompt(wo: dict[str, Any], project: dict[str, Any]) -> str:
    """Build the complete prompt for the specialist agent."""
    specialist = wo.get("specialist", "IDD-4")
    system = SPECIALIST_PROMPTS.get(specialist, SPECIALIST_PROMPTS["IDD-4"])
    repo = project.get("repo", "")
    stack = ", ".join(project.get("stack", []))
    deployments = project.get("deployments", {})
    sandbox_url = deployments.get("frontend", "")

    return (
        f"{system}\n\n"
        f"== WORK ORDER ==\n"
        f"Project: {wo['project_id']}\n"
        f"Repo: {repo}\n"
        f"Stack: {stack}\n"
        f"Failure type: {wo['failure_type']}\n"
        f"Severity: {wo['severity']}\n"
        f"Linear ticket: {wo['linear_ticket_id']}\n\n"
        f"Issue description:\n{wo['description']}\n\n"
        f"== YOUR TASK ==\n"
        f"1. Clone / read the repo at {repo}\n"
        f"2. Diagnose the root cause of the issue\n"
        f"3. Apply the minimal surgical fix\n"
        f"4. Create a PR from a feature branch named "
        f"   fix/{wo['failure_type']}-{wo['linear_ticket_id'].lower()}\n"
        f"5. The PR title must start with '[AutoFix]'\n"
        f"6. Verify CI passes on the PR branch\n"
        f"7. Report: what you found, what you changed, PR URL\n\n"
        f"Sandbox URL (Vercel preview): {sandbox_url}\n"
        f"DO NOT merge to main. The Board will review and approve the merge.\n"
        f"DO NOT change anything outside the scope of the reported issue.\n"
    )


def _dispatch_specialist(wo: dict[str, Any],
                          project: dict[str, Any]) -> FixJob | None:
    """Spawn a Claude Code session to fix the work order."""
    specialist = wo.get("specialist", "IDD-4")
    prompt = _build_fix_prompt(wo, project)
    job_id = (
        f"fix-{wo['project_id']}-"
        f"{date.today().isoformat()}-{wo['linear_ticket_id']}"
    )

    job = FixJob(
        job_id=job_id,
        work_order_id=job_id,
        project_id=wo["project_id"],
        failure_type=wo["failure_type"],
        severity=wo["severity"],
        description=wo["description"][:200],
        specialist=specialist,
        linear_ticket_id=wo["linear_ticket_id"],
        status="dispatched",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Attempt to invoke via Pi-CEO session (provider_router)
    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415
        import asyncio  # noqa: PLC0415

        async def _run() -> tuple[int, str, float, str | None]:
            return await run_via_provider(
                prompt=prompt,
                role="orchestrator",
                timeout_s=300,
                session_id=job_id,
                thinking="adaptive",
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures  # noqa: PLC0415
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                rc, response, _cost, err = ex.submit(asyncio.run, _run()).result(timeout=360)
        else:
            rc, response, _cost, err = asyncio.run(_run())

        if rc == 0 and not err:
            job.status = "fixing"
            # Try to extract PR URL from response
            import re as _re  # noqa: PLC0415
            pr_match = _re.search(r'https://github\.com/\S+/pull/\d+', response)
            if pr_match:
                job.pr_url = pr_match.group()
                job.status = "pr_created"
                log.info("fix_orchestrator: %s created PR %s", specialist, job.pr_url)
        else:
            job.status = "failed"
            log.warning("fix_orchestrator: %s failed for %s — %s",
                        specialist, job.job_id, err or f"rc={rc}")

    except Exception as exc:  # noqa: BLE001
        log.warning("fix_orchestrator: dispatch raised for %s (%s)", job.job_id, exc)
        job.status = "failed"

    _save_job(job)
    return job


def _route_to_board(job: FixJob) -> str | None:
    """Queue a Board review session for a completed fix."""
    if not job.pr_url:
        return None
    try:
        from . import board as _board  # noqa: PLC0415
        session_id = _board.from_margot(
            topic=f"Production gate: {job.project_id} — {job.failure_type}",
            insight=(
                f"AutoFix agent {job.specialist} has created a PR for "
                f"{job.project_id} ({job.failure_type}, severity={job.severity}).\n\n"
                f"PR: {job.pr_url}\n"
                f"Sandbox: {job.sandbox_url or 'Vercel preview pending'}\n\n"
                f"Linear ticket: {job.linear_ticket_id}\n\n"
                f"Review the diff and preview. Approve to merge to main (production). "
                f"Reject to send back to the specialist with notes."
            ),
            citations=[job.pr_url],
        )
        return session_id
    except Exception as exc:  # noqa: BLE001
        log.warning("fix_orchestrator: board routing failed (%s)", exc)
        return None


def run_cycle(repo_root: Path | None = None) -> OrchestratorResult:
    """Check for new work orders, dispatch specialists, route completed fixes to Board."""
    result = OrchestratorResult()

    # Load active jobs to check cap
    active = _load_active_jobs()
    active_dispatched = [j for j in active if j.status == "dispatched"]

    if len(active_dispatched) >= MAX_ACTIVE_FIXES:
        log.info("fix_orchestrator: %d active jobs at cap — skipping new dispatches",
                 len(active_dispatched))
    else:
        # Fetch open work-order tickets from Linear
        open_tickets = _fetch_open_work_orders()
        # Exclude tickets already being worked
        active_ticket_ids = {j.linear_ticket_id for j in active}
        new_tickets = [t for t in open_tickets
                       if t.get("identifier") not in active_ticket_ids]

        # Load project registry for context
        projects_json = _repo_root() / ".harness" / "projects.json"
        projects_map: dict[str, dict] = {}
        if projects_json.exists():
            for p in json.loads(projects_json.read_text()).get("projects", []):
                projects_map[p["id"]] = p

        # Dispatch up to the cap
        slots = MAX_ACTIVE_FIXES - len(active_dispatched)
        for ticket in new_tickets[:slots]:
            wo = _parse_work_order_from_ticket(ticket)
            if not wo:
                continue
            project = projects_map.get(wo["project_id"], {})
            job = _dispatch_specialist(wo, project)
            if job:
                result.jobs_dispatched.append(job.job_id)
                log.info("fix_orchestrator: dispatched %s → %s for %s",
                         job.job_id, job.specialist, job.project_id)

    # Route PR-created jobs to Board (if not already queued)
    for job in active:
        if job.status == "pr_created" and not job.board_session_id:
            session_id = _route_to_board(job)
            if session_id:
                job.board_session_id = session_id
                job.status = "board_pending"
                _save_job(job)
                result.board_sessions_queued.append(session_id)
                log.info("fix_orchestrator: routed %s to Board session %s",
                         job.job_id, session_id)

    return result


__all__ = ["run_cycle", "should_run", "FixJob", "OrchestratorResult"]
