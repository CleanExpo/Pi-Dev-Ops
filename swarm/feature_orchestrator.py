"""swarm/feature_orchestrator.py — routes `margot-idea` Backlog tickets to
specialist Claude Code agents, manages the feature-ship lifecycle: triage
→ dispatch → PR → review → done.

This is the third lane of the swarm — sibling to `fix_orchestrator.py`
(bug-fix lane) and the PM bots (planning/recon lane). It exists to close
the autonomous-shipping gap: 36 `margot-idea` tickets were sitting in
Backlog forever because nothing was wired to pick them up.

Public API:
    run_cycle(repo_root) -> OrchestratorResult
    should_run(state)    -> bool
    triage_specialist(title, description) -> str
    triage_complexity(title, description) -> str

Structural pattern mirrors `fix_orchestrator.py` — same dataclasses,
same logging tag, same return shape, same state-as-JSONL persistence.
Deliberately NOT a refactor of fix_orchestrator — the two lanes have
different ticket sources, different prompts, different lifecycles.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.feature_orchestrator")

STATE_KEY = "last_feature_orchestrator"
MAX_ACTIVE_FEATURES = 2   # concurrent specialist agents cap — narrower than fix lane
CYCLE_MIN_INTERVAL_S = 30 * 60   # 30 minutes between cycles
MAX_FAILED_ATTEMPTS = 3   # park after 3 failures

# Default label filter (override via FEATURE_ORCH_LABEL env var).
DEFAULT_FEATURE_LABEL = "margot-idea"

# Active statuses — a job in any of these states blocks new dispatches.
ACTIVE_STATUSES: tuple[str, ...] = ("dispatched", "pr_open", "in_review")

# Specialist → skill allowlist (mirrors fix_orchestrator.SPECIALIST_SKILLS;
# kept local so the bug-fix lane stays untouched per task rules).
FEATURE_SPECIALIST_SKILLS: dict[str, list[str]] = {
    "IDD-3": ["read", "edit", "write", "bash_python", "create_pr"],
    "IDD-4": ["read", "edit", "write", "bash_node", "create_pr"],
    "IDD-5": ["read", "edit", "write", "bash_infra", "vercel_cli", "create_pr"],
    "SD-1":  ["read", "edit", "write", "bash_sql", "create_pr"],
    "SD-4":  ["read", "edit", "write", "xcode_cli", "create_pr"],
}

# Feature-shipping prompts — distinct from fix-lane prompts. Tone is
# "build the small new thing", not "diagnose and fix the broken thing".
FEATURE_SPECIALIST_PROMPTS: dict[str, str] = {
    "IDD-3": (
        "You are IDD-3, a senior Python/FastAPI engineer with 15+ years experience. "
        "You own Pi-CEO swarm (Python), CCW-CRM backend (FastAPI), and all Python services. "
        "Ship the requested feature as the minimum viable increment. Follow existing patterns. "
        "Add tests. No speculative abstractions. One PR per ticket."
    ),
    "IDD-4": (
        "You are IDD-4, a senior TypeScript/Next.js engineer with 15+ years experience. "
        "You own all Next.js frontends across the portfolio. Ship the requested UI / page / "
        "copy change with surgical precision. Match existing design tokens (Gun Metal + Candy "
        "Red on the dashboard). No Lucide icons. Add tests where the change has logic."
    ),
    "IDD-5": (
        "You are IDD-5, a senior infrastructure and DevOps engineer. "
        "You own Railway, Vercel, Supabase, GitHub Actions across all 11 projects. "
        "Ship the requested infra change as a reviewable PR. Document every env var. "
        "Sandbox-validate before requesting merge."
    ),
    "SD-1": (
        "You are SD-1, a senior database architect with deep Supabase/Postgres expertise. "
        "Ship the requested schema / migration / RLS change. Every migration must be "
        "reversible. Include the rollback SQL in the PR description."
    ),
    "SD-4": (
        "You are SD-4, a senior mobile platform specialist. "
        "You own RestoreAssist iOS — App Store pipeline, TestFlight, Swift/React Native. "
        "Ship the requested mobile feature as a TestFlight-ready build."
    ),
}

# Maps project_slug → project_id in .harness/projects.json. Populated lazily.
_PROJECT_INDEX: dict[str, dict[str, Any]] | None = None


@dataclass
class FeatureJob:
    linear_id: str                       # e.g. UNI-2014
    title: str
    description: str
    priority: int                        # 1=urgent, 2=high, 3=med, 4=low
    project_slug: str                    # which repo to ship into
    labels: list[str] = field(default_factory=list)
    complexity: str = "m"                # 's' | 'm' | 'l' | 'xl'
    specialist: str = "IDD-3"            # IDD-3 | IDD-4 | IDD-5 | SD-1 | SD-4
    status: str = "triaging"             # triaging | dispatched | pr_open | in_review | done | failed | parked | needs_planning
    pr_url: str | None = None
    error: str | None = None
    failed_attempts: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OrchestratorResult:
    jobs_dispatched: list[str] = field(default_factory=list)
    jobs_completed: list[str] = field(default_factory=list)
    jobs_failed: list[str] = field(default_factory=list)
    jobs_parked: list[str] = field(default_factory=list)
    jobs_needing_plan: list[str] = field(default_factory=list)
    error: str | None = None


# ─── Cadence gate ──────────────────────────────────────────────────────────

def should_run(state: dict) -> bool:
    """Run every ~30 min. Same cadence shape as the fix lane but explicit
    interval gating — the feature lane is more expensive per cycle (LLM
    triage + repo clones) so we don't run it every 5-min orchestrator tick.
    """
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return True
    age_s = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return age_s >= CYCLE_MIN_INTERVAL_S


# ─── Pure-function triage ──────────────────────────────────────────────────

# Trigger patterns — checked top-to-bottom, first match wins. Each pattern is
# a case-insensitive substring or regex against the combined "title + body".
_SPECIALIST_TRIGGERS: tuple[tuple[str, str], ...] = (
    # database / migrations — checked BEFORE infra so "migration" doesn't
    # get caught by a generic "deploy" trigger
    ("SD-1", r"\b(migration|schema|rls|supabase\s+sql|postgres|sql\s+query|alter\s+table|create\s+table|database)\b"),
    # iOS / mobile
    ("SD-4", r"\b(ios|capacitor|swift|testflight|app\s*store|xcode|react\s+native)\b"),
    # infra / vercel / railway / CI
    ("IDD-5", r"\b(vercel|railway|supabase\s+project|github\s+action|ci\s+config|deploy|env\s*var|infra|dns|cdn|cron|launchagent)\b"),
    # frontend signals — checked LAST among UI patterns so backend "API"
    # mentions can still win below
    ("IDD-4", r"\b(ui|page|copy|landing|tailwind|next\.?js\s+page|component|design|dashboard\s+screen|frontend\s*only)\b"),
)

# Backend default trigger — explicit so it shows up in the rules table even
# though the resolution is "fall through to default".
_BACKEND_DEFAULT = "IDD-3"


def triage_specialist(title: str, description: str) -> str:
    """Pure function — classify which specialist should ship this ticket.

    Order matters: SD-1 (DB) → SD-4 (mobile) → IDD-5 (infra) → IDD-4 (frontend)
    → IDD-3 (backend default). Backend is the catch-all.
    """
    haystack = f"{title or ''}\n{description or ''}".lower()
    for specialist, pattern in _SPECIALIST_TRIGGERS:
        if re.search(pattern, haystack):
            return specialist
    return _BACKEND_DEFAULT


def triage_complexity(title: str, description: str) -> str:
    """Pure function — bucket size estimation from title + description.

    Heuristic:
      - "phase N" / "epic" / "multi-week" mentions      → xl  (will be parked)
      - 500+ words OR mentions multiple subsystems       → l   (needs planning)
      - 100–500 words                                     → m
      - <100 words and no API/migration mentioned        → s
    """
    text = f"{title or ''}\n{description or ''}"
    lower = text.lower()

    # xl — explicit epic markers
    epic_markers = (r"\bphase\s+\d+\b", r"\bepic\b", r"\bmulti-?week\b", r"\bmilestone\b")
    if any(re.search(p, lower) for p in epic_markers):
        return "xl"

    word_count = len(re.findall(r"\w+", text))

    # multi-subsystem detector — counts distinct system tokens
    subsystems = {
        "frontend": r"\b(frontend|ui|page|tailwind|component)\b",
        "backend":  r"\b(backend|api|fastapi|python|endpoint)\b",
        "database": r"\b(database|migration|schema|sql|supabase\s+sql)\b",
        "infra":    r"\b(vercel|railway|deploy|ci|github\s+action)\b",
        "mobile":   r"\b(ios|capacitor|swift|testflight)\b",
    }
    distinct_systems = sum(
        1 for pat in subsystems.values() if re.search(pat, lower)
    )

    if word_count >= 500 or distinct_systems >= 3:
        return "l"
    if word_count >= 100:
        return "m"

    # s — but only if no API/migration mention (these expand under the hood)
    api_or_migration = re.search(r"\b(api|endpoint|migration|schema)\b", lower)
    if api_or_migration:
        return "m"
    return "s"


# ─── Project routing ───────────────────────────────────────────────────────

# Maps common slug aliases that might appear in a margot-idea ticket
# description / title to canonical project_ids in .harness/projects.json.
_PROJECT_ALIASES: dict[str, str] = {
    "ra": "restoreassist",
    "restoreassist": "restoreassist",
    "dr": "disaster-recovery",
    "disaster-recovery": "disaster-recovery",
    "nrpg": "dr-nrpg",
    "dr-nrpg": "dr-nrpg",
    "carsi": "carsi",
    "ccw": "ccw-crm",
    "ccw-crm": "ccw-crm",
    "synthex": "synthex",
    "pi-dev-ops": "pi-dev-ops",
    "pi-ceo": "pi-dev-ops",
}


def _detect_project_slug(title: str, description: str) -> str:
    """Best-effort: pull the target project slug out of title + body.
    Defaults to 'pi-dev-ops' (the swarm itself) if nothing matches —
    most margot-idea tickets target the swarm by default.
    """
    haystack = f"{title or ''}\n{description or ''}".lower()
    # Score each alias by occurrence count, longest alias wins on tie
    best: tuple[int, int, str] = (0, 0, "pi-dev-ops")
    for alias, canon in _PROJECT_ALIASES.items():
        hits = len(re.findall(rf"\b{re.escape(alias)}\b", haystack))
        if hits == 0:
            continue
        score = (hits, len(alias), canon)
        if score > best:
            best = score
    return best[2]


def _load_project_index() -> dict[str, dict[str, Any]]:
    """Lazy-load .harness/projects.json keyed by project id."""
    global _PROJECT_INDEX
    if _PROJECT_INDEX is not None:
        return _PROJECT_INDEX
    p = _repo_root() / ".harness" / "projects.json"
    if not p.exists():
        _PROJECT_INDEX = {}
        return _PROJECT_INDEX
    try:
        raw = json.loads(p.read_text())
        _PROJECT_INDEX = {
            proj["id"]: proj for proj in raw.get("projects", [])
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("feature_orchestrator: projects.json parse failed (%s)", exc)
        _PROJECT_INDEX = {}
    return _PROJECT_INDEX


# ─── State helpers ─────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _jobs_log() -> Path:
    p = _repo_root() / ".harness" / "swarm" / "feature_jobs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_jobs_index() -> dict[str, FeatureJob]:
    """Load latest-state per linear_id from append-only JSONL."""
    log_path = _jobs_log()
    if not log_path.exists():
        return {}
    jobs: dict[str, FeatureJob] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            job = FeatureJob(**{
                k: v for k, v in row.items()
                if k in FeatureJob.__dataclass_fields__
            })
            jobs[job.linear_id] = job
        except Exception:  # noqa: BLE001
            continue
    return jobs


def _save_job(job: FeatureJob) -> None:
    job.updated_at = datetime.now(timezone.utc).isoformat()
    with _jobs_log().open("a", encoding="utf-8") as f:
        f.write(json.dumps(job.__dict__) + "\n")


# ─── Linear integration ────────────────────────────────────────────────────

def _fetch_eligible_tickets(label: str) -> list[dict[str, Any]]:
    """Fetch Backlog/Todo tickets tagged with `label`, priority 1 or 2."""
    try:
        from .margot_tools import _linear_gql  # noqa: PLC0415
        res = _linear_gql(
            """query($label: String!) {
                issues(filter: {
                    labels: {name: {eq: $label}},
                    state: {type: {in: ["backlog", "unstarted"]}},
                    priority: {in: [1, 2]}
                }, first: 50, orderBy: updatedAt) {
                    nodes {
                        id identifier title description priority createdAt
                        labels { nodes { name } }
                    }
                }
            }""",
            {"label": label},
        )
        if "error" in res:
            log.warning("feature_orchestrator: Linear fetch error: %s", res.get("error"))
            return []
        return (res.get("data") or {}).get("issues", {}).get("nodes", []) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("feature_orchestrator: Linear fetch failed (%s)", exc)
        return []


def _move_ticket_to_in_review(linear_id: str) -> None:
    """Update the Linear ticket state to 'In Review'. Fail-soft."""
    try:
        from .margot_tools import _linear_gql  # noqa: PLC0415
        # Resolve state id by name first
        state_res = _linear_gql(
            """query { workflowStates(filter: {name: {eq: "In Review"}}, first: 5) {
                nodes { id name } } }"""
        )
        states = (state_res.get("data") or {}).get("workflowStates", {}).get("nodes", []) or []
        if not states:
            return
        state_id = states[0]["id"]
        _linear_gql(
            """mutation($id: String!, $stateId: String!) {
                issueUpdate(id: $id, input: {stateId: $stateId}) {
                    success
                }
            }""",
            {"id": linear_id, "stateId": state_id},
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("feature_orchestrator: state update skipped (%s)", exc)


# ─── Telegram alerts ───────────────────────────────────────────────────────

def _alert(tag: str, body: str, severity: str = "info") -> None:
    """Send a tagged Telegram alert to the 'dev' channel. Fail-soft.

    RA-2232: routed to the dev bot so PR-opened / CI / specialist-progress
    pings stop spamming Phill's general Margot inbox. Falls back to general
    with a "[fallback from dev]" tag until Phill mints the dev bot.
    """
    try:
        from .telegram_router import send  # noqa: PLC0415
        send(
            f"[FEATURE-ORCH:{tag}] {body}",
            channel="dev",
            severity=severity,
            bot_name="FeatureOrchestrator",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("feature_orchestrator: telegram alert skipped (%s)", exc)


# ─── Dispatch ──────────────────────────────────────────────────────────────

def _build_feature_prompt(job: FeatureJob, project: dict[str, Any]) -> str:
    """Compose the full prompt sent to the specialist."""
    system = FEATURE_SPECIALIST_PROMPTS.get(
        job.specialist, FEATURE_SPECIALIST_PROMPTS["IDD-3"]
    )
    repo = project.get("repo", f"<unknown:{job.project_slug}>")
    stack = ", ".join(project.get("stack", []))
    deployments = project.get("deployments", {})
    sandbox_url = deployments.get("frontend", "")

    branch = f"feat/{job.linear_id.lower()}"

    return (
        f"{system}\n\n"
        f"== FEATURE TICKET ==\n"
        f"Linear: {job.linear_id}\n"
        f"Title: {job.title}\n"
        f"Project: {job.project_slug}\n"
        f"Repo: {repo}\n"
        f"Stack: {stack}\n"
        f"Priority: {job.priority}\n"
        f"Complexity bucket: {job.complexity}\n"
        f"Labels: {', '.join(job.labels)}\n\n"
        f"Description:\n{job.description}\n\n"
        f"== YOUR TASK ==\n"
        f"1. Read the repo at {repo}\n"
        f"2. Implement the minimum viable increment of the feature\n"
        f"3. Create a PR from branch `{branch}`\n"
        f"4. PR title must start with '[Feature] ' and reference {job.linear_id}\n"
        f"5. Verify CI passes on the PR branch\n"
        f"6. Report PR URL when done\n\n"
        f"Sandbox URL: {sandbox_url or '(no preview configured)'}\n"
        f"DO NOT merge to main — the Board will gate production.\n"
        f"DO NOT add work outside the ticket scope. One PR per ticket.\n"
    )


def _shadow_mode() -> bool:
    return os.environ.get("TAO_SWARM_SHADOW", "0") == "1"


def _dispatch_specialist(job: FeatureJob, project: dict[str, Any]) -> FeatureJob:
    """Spawn (or dry-run-print) a Claude Code session for this feature job."""
    prompt = _build_feature_prompt(job, project)

    if _shadow_mode():
        # Dry-run path — print and mark dispatched-shadow without firing.
        print(
            f"would-dispatch: {job.linear_id} → {job.specialist} "
            f"({job.complexity}) — project={job.project_slug}"
        )
        job.status = "dispatched"
        job.error = "shadow_mode"
        _save_job(job)
        return job

    try:
        from app.server.provider_router import run_via_provider  # noqa: PLC0415

        session_id = (
            f"feat-{job.project_slug}-{date.today().isoformat()}-{job.linear_id}"
        )

        async def _run() -> tuple[int, str, float, str | None]:
            return await run_via_provider(
                prompt=prompt,
                role="orchestrator",
                timeout_s=600,
                session_id=session_id,
                thinking="adaptive",
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures  # noqa: PLC0415
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                rc, response, _cost, err = ex.submit(
                    asyncio.run, _run()
                ).result(timeout=660)
        else:
            rc, response, _cost, err = asyncio.run(_run())

        if rc == 0 and not err:
            job.status = "dispatched"
            pr_match = re.search(r"https://github\.com/\S+/pull/\d+", response)
            if pr_match:
                job.pr_url = pr_match.group()
                job.status = "pr_open"
                log.info(
                    "feature_orchestrator: %s opened PR %s for %s",
                    job.specialist, job.pr_url, job.linear_id,
                )
        else:
            job.status = "failed"
            job.error = err or f"rc={rc}"
            job.failed_attempts += 1
            log.warning(
                "feature_orchestrator: %s failed for %s — %s",
                job.specialist, job.linear_id, job.error,
            )
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = repr(exc)
        job.failed_attempts += 1
        log.warning(
            "feature_orchestrator: dispatch raised for %s (%s)",
            job.linear_id, exc,
        )

    _save_job(job)
    return job


# ─── Triage → Job pipeline ─────────────────────────────────────────────────

def _build_job_from_ticket(ticket: dict[str, Any]) -> FeatureJob:
    """Compose a FeatureJob from a Linear ticket node + run triage."""
    linear_id = ticket.get("identifier", "")
    title = ticket.get("title", "") or ""
    description = ticket.get("description", "") or ""
    priority = int(ticket.get("priority") or 3)
    labels = [
        lbl.get("name", "")
        for lbl in (ticket.get("labels", {}) or {}).get("nodes", [])
    ]

    return FeatureJob(
        linear_id=linear_id,
        title=title,
        description=description,
        priority=priority,
        project_slug=_detect_project_slug(title, description),
        labels=labels,
        complexity=triage_complexity(title, description),
        specialist=triage_specialist(title, description),
        status="triaging",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Main cycle ────────────────────────────────────────────────────────────

def run_cycle(repo_root: Path | None = None) -> OrchestratorResult:
    """Poll Linear for margot-idea Backlog tickets, triage, dispatch up to
    MAX_ACTIVE_FEATURES, manage lifecycle transitions. Idempotent.
    """
    result = OrchestratorResult()

    label = os.environ.get("FEATURE_ORCH_LABEL", DEFAULT_FEATURE_LABEL)

    # Load existing job state to enforce concurrency + retry caps
    jobs_by_id = _load_jobs_index()
    active = [j for j in jobs_by_id.values() if j.status in ACTIVE_STATUSES]

    if len(active) >= MAX_ACTIVE_FEATURES:
        log.info(
            "feature_orchestrator: %d active jobs at cap (%d) — skipping new dispatches",
            len(active), MAX_ACTIVE_FEATURES,
        )
        return result

    tickets = _fetch_eligible_tickets(label)
    if not tickets:
        log.info("feature_orchestrator: no eligible tickets for label '%s'", label)
        return result

    projects_index = _load_project_index()
    slots = MAX_ACTIVE_FEATURES - len(active)
    dispatched_count = 0

    for ticket in tickets:
        if dispatched_count >= slots:
            break

        linear_id = ticket.get("identifier", "")
        prior = jobs_by_id.get(linear_id)

        # Skip if currently active
        if prior and prior.status in ACTIVE_STATUSES:
            continue
        # Skip if already done
        if prior and prior.status == "done":
            continue
        # Skip if parked
        if prior and prior.status == "parked":
            continue
        # Cap retries
        if prior and prior.failed_attempts >= MAX_FAILED_ATTEMPTS:
            if prior.status != "parked":
                prior.status = "parked"
                prior.error = (
                    f"{MAX_FAILED_ATTEMPTS} attempts failed: "
                    f"{prior.error or 'unknown'}"
                )
                _save_job(prior)
                result.jobs_parked.append(prior.linear_id)
            continue

        job = _build_job_from_ticket(ticket)
        # Preserve retry counter across cycles
        if prior:
            job.failed_attempts = prior.failed_attempts

        # xl → park, no alert
        if job.complexity == "xl":
            job.status = "parked"
            job.error = "complexity=xl (epic-scale — needs decomposition)"
            _save_job(job)
            result.jobs_parked.append(job.linear_id)
            log.info(
                "feature_orchestrator: parked %s (xl complexity)",
                job.linear_id,
            )
            continue

        # l → needs_planning, alert PM
        if job.complexity == "l":
            job.status = "needs_planning"
            _save_job(job)
            result.jobs_needing_plan.append(job.linear_id)
            _alert(
                "PLAN",
                f"{job.linear_id} '{job.title[:60]}' is complexity=l — "
                f"requesting PM decomposition before dispatch.",
                severity="info",
            )
            log.info(
                "feature_orchestrator: flagged %s for PM planning",
                job.linear_id,
            )
            continue

        # s and m → dispatch
        project = projects_index.get(job.project_slug, {})
        job = _dispatch_specialist(job, project)
        dispatched_count += 1

        if job.status == "failed":
            # Cycle back to Backlog (don't keep retrying same cycle) but
            # increment failed_attempts so MAX_FAILED_ATTEMPTS eventually parks it
            result.jobs_failed.append(job.linear_id)
            _alert(
                "FAIL",
                f"{job.linear_id} '{job.title[:60]}' failed via "
                f"{job.specialist}: {job.error}",
                severity="high",
            )
        else:
            result.jobs_dispatched.append(job.linear_id)
            log.info(
                "feature_orchestrator: dispatched %s → %s (%s)",
                job.linear_id, job.specialist, job.complexity,
            )

    # Lifecycle: surface PR-open transitions to Linear (best-effort)
    for job in jobs_by_id.values():
        if job.status == "pr_open" and job.pr_url:
            _move_ticket_to_in_review(job.linear_id)
            job.status = "in_review"
            _save_job(job)

    return result


# ─── CLI entry ─────────────────────────────────────────────────────────────

def _main() -> None:
    """`python -m swarm.feature_orchestrator` — runs a single cycle.
    In TAO_SWARM_SHADOW=1 mode, prints would-dispatch lines instead of firing.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )
    res = run_cycle()
    print(json.dumps({
        "dispatched": res.jobs_dispatched,
        "failed":     res.jobs_failed,
        "parked":     res.jobs_parked,
        "needs_plan": res.jobs_needing_plan,
    }, indent=2))


if __name__ == "__main__":
    _main()


__all__ = [
    "run_cycle",
    "should_run",
    "triage_specialist",
    "triage_complexity",
    "FeatureJob",
    "OrchestratorResult",
    "MAX_ACTIVE_FEATURES",
    "MAX_FAILED_ATTEMPTS",
    "DEFAULT_FEATURE_LABEL",
    "FEATURE_SPECIALIST_PROMPTS",
    "FEATURE_SPECIALIST_SKILLS",
]
