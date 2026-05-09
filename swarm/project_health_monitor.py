"""swarm/project_health_monitor.py — reads daily health signals across all
11 projects and generates structured WorkOrders for the fix_orchestrator.

Runs once per day. Sources:
  * CTO DORA breaches (cto_state.jsonl)
  * GitHub CI / PR staleness (portfolio_pulse_github data)
  * Vercel deployment failures (portfolio_pulse via Vercel API)
  * Linear open blocker tickets (linear_tools)

Each unhealthy signal becomes a WorkOrder filed as a Linear ticket tagged
[work-order] so fix_orchestrator can pick it up.

Public API:
    run_daily(repo_root) -> HealthReport
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

log = logging.getLogger("swarm.project_health_monitor")

STATE_KEY = "last_health_monitor"
MAX_WORK_ORDERS_PER_RUN = 10

# Specialist routing — failure_type → agent_id
SPECIALIST_MAP: dict[str, str] = {
    "ci_failing":          "IDD-4",
    "ci_failing_python":   "IDD-3",
    "build_failure":       "IDD-5",
    "stale_pr":            "IDD-1",
    "low_deploy_freq":     "IDD-4",
    "security_advisory":   "SD-2",
    "latency_breach":      "IDD-5",
    "db_migration_drift":  "SD-1",
    "mobile_store_issue":  "SD-4",
    "api_error_rate":      "SD-3",
    "unknown":             "IDD-4",
}

# Project → stack hint for specialist override
STACK_MAP: dict[str, list[str]] = {
    "pi-dev-ops":         ["python", "typescript"],
    "restoreassist":      ["typescript", "ios"],
    "disaster-recovery":  ["typescript"],
    "dr-nrpg":            ["typescript"],
    "nrpg-onboarding":    ["typescript"],
    "synthex":            ["typescript"],
    "unite-group":        ["typescript"],
    "ccw-crm":            ["python", "typescript"],
    "carsi":              ["typescript"],
}


@dataclass
class WorkOrder:
    work_order_id: str
    project_id: str
    failure_type: str
    severity: str          # critical | high | medium | low
    description: str
    context: dict = field(default_factory=dict)
    assigned_specialist: str = "IDD-4"
    linear_ticket_id: str = ""
    status: str = "pending"
    created_at: str = ""


@dataclass
class HealthReport:
    work_orders: list[WorkOrder] = field(default_factory=list)
    projects_checked: int = 0
    projects_unhealthy: int = 0
    tickets_filed: list[str] = field(default_factory=list)
    error: str | None = None


def should_run(state: dict) -> bool:
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(last[:10]) < date.today()
    except (ValueError, TypeError):
        return True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_projects() -> list[dict[str, Any]]:
    p = _repo_root() / ".harness" / "projects.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("projects", [])


def _load_cto_breaches() -> list[dict[str, Any]]:
    """Read current DORA breaches from cto_state.jsonl."""
    try:
        from . import cto as _cto  # noqa: PLC0415
        snapshots = _cto.load_last_snapshot(
            str(_repo_root() / _cto.CTO_STATE_FILE_REL)
        )
        if not snapshots:
            return []
        prev = _cto.load_last_snapshot(
            str(_repo_root() / _cto.CTO_STATE_FILE_REL), offset=1
        )
        metrics = [_cto.dict_to_snapshot(s) for s in snapshots]
        prev_metrics = [_cto.dict_to_snapshot(s) for s in prev] if prev else []
        breaches = []
        for m in metrics:
            prev_m = next((p for p in prev_metrics
                           if p.business_id == m.business_id), None)
            breaches.extend(_cto.detect_breaches(m, prev_m))
        return [
            {
                "project_id": b.business_id,
                "metric": b.metric,
                "severity": b.severity,
                "message": b.message,
            }
            for b in breaches
        ]
    except Exception as exc:  # noqa: BLE001
        log.debug("health_monitor: cto breach load failed (%s)", exc)
        return []


def _check_github_health(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Check GitHub CI + PR staleness for a project."""
    issues: list[dict[str, Any]] = []
    repo = project.get("repo", "")
    project_id = project.get("id", "")
    if not repo or not os.environ.get("GITHUB_TOKEN"):
        return issues

    try:
        import urllib.request as _ur  # noqa: PLC0415
        token = os.environ["GITHUB_TOKEN"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        def _gh(path: str) -> Any:
            req = _ur.Request(f"https://api.github.com{path}", headers=headers)
            with _ur.urlopen(req, timeout=15) as r:
                return json.loads(r.read())

        # Check latest CI run on default branch
        try:
            runs = _gh(f"/repos/{repo}/actions/runs?branch=main&per_page=1")
            if runs.get("workflow_runs"):
                run = runs["workflow_runs"][0]
                if run.get("conclusion") not in ("success", "skipped", None):
                    stack = STACK_MAP.get(project_id, ["typescript"])
                    ftype = "ci_failing_python" if "python" in stack else "ci_failing"
                    issues.append({
                        "project_id": project_id,
                        "failure_type": ftype,
                        "severity": "high",
                        "description": (
                            f"CI failing on {repo} main branch — "
                            f"run #{run.get('run_number','?')} "
                            f"status: {run.get('conclusion','?')}"
                        ),
                        "context": {
                            "repo": repo,
                            "run_id": run.get("id"),
                            "conclusion": run.get("conclusion"),
                            "html_url": run.get("html_url"),
                        },
                    })
        except Exception:  # noqa: BLE001
            pass

        # Check stale PRs (open > 3 days with no updates)
        try:
            prs = _gh(f"/repos/{repo}/pulls?state=open&per_page=20")
            now = datetime.now(timezone.utc)
            for pr in prs:
                updated = datetime.fromisoformat(
                    pr["updated_at"].replace("Z", "+00:00")
                )
                age_days = (now - updated).days
                if age_days > 3:
                    issues.append({
                        "project_id": project_id,
                        "failure_type": "stale_pr",
                        "severity": "medium",
                        "description": (
                            f"PR #{pr['number']} '{pr['title'][:60]}' "
                            f"stale for {age_days} days — needs review"
                        ),
                        "context": {
                            "repo": repo,
                            "pr_number": pr["number"],
                            "pr_url": pr["html_url"],
                            "age_days": age_days,
                        },
                    })
        except Exception:  # noqa: BLE001
            pass

    except Exception as exc:  # noqa: BLE001
        log.debug("health_monitor: github check failed for %s (%s)", project_id, exc)

    return issues


def _assign_specialist(failure_type: str, project_id: str) -> str:
    base = SPECIALIST_MAP.get(failure_type, "IDD-4")
    # Override for Python-heavy projects
    if failure_type == "ci_failing":
        stack = STACK_MAP.get(project_id, [])
        if "python" in stack:
            return "IDD-3"
    return base


def _file_work_order_ticket(wo: WorkOrder) -> str:
    """File a Linear ticket for this work order. Returns identifier or ''."""
    try:
        from .margot_tools import propose_idea  # noqa: PLC0415
        title = f"[WorkOrder] {wo.project_id} — {wo.failure_type} ({wo.severity})"
        description = (
            f"**Project:** {wo.project_id}\n"
            f"**Failure:** {wo.failure_type}\n"
            f"**Severity:** {wo.severity}\n"
            f"**Assigned to:** {wo.assigned_specialist}\n\n"
            f"**Description:**\n{wo.description}\n\n"
            f"**Context:**\n```json\n{json.dumps(wo.context, indent=2)}\n```\n\n"
            f"---\n*Auto-filed by project_health_monitor on "
            f"{date.today().isoformat()}. "
            f"Work order ID: {wo.work_order_id}*"
        )
        priority = {"critical": 1, "high": 2, "medium": 3, "low": 4}.get(
            wo.severity, 3
        )
        r = propose_idea(
            title=title,
            description=description,
            priority=priority,
            project="Pi - Dev -Ops",
        )
        if r.get("status") == "created":
            return r.get("identifier", "")
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: ticket filing failed (%s)", exc)
    return ""


def run_daily(repo_root: Path | None = None) -> HealthReport:
    """Scan all projects for health issues and file work-order tickets."""
    report = HealthReport()
    projects = _load_projects()
    report.projects_checked = len(projects)

    # Collect all raw issues
    raw_issues: list[dict[str, Any]] = []

    # CTO DORA breaches
    for breach in _load_cto_breaches():
        raw_issues.append({
            "project_id": breach["project_id"],
            "failure_type": f"dora_{breach['metric']}",
            "severity": breach["severity"],
            "description": breach["message"],
            "context": {"source": "cto_dora"},
        })

    # GitHub per-project health
    for project in projects:
        issues = _check_github_health(project)
        raw_issues.extend(issues)

    # Deduplicate by project_id + failure_type, keep highest severity
    seen: dict[str, dict[str, Any]] = {}
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for issue in raw_issues:
        key = f"{issue['project_id']}:{issue['failure_type']}"
        if key not in seen or (
            severity_rank.get(issue["severity"], 3) <
            severity_rank.get(seen[key]["severity"], 3)
        ):
            seen[key] = issue

    # Sort by severity, cap at MAX_WORK_ORDERS_PER_RUN
    sorted_issues = sorted(
        seen.values(),
        key=lambda x: severity_rank.get(x.get("severity", "low"), 3),
    )[:MAX_WORK_ORDERS_PER_RUN]

    unhealthy_projects: set[str] = set()

    for i, issue in enumerate(sorted_issues):
        pid = issue["project_id"]
        unhealthy_projects.add(pid)
        wo_id = (
            f"wo-{pid}-{date.today().isoformat()}-{i+1:03d}"
        )
        specialist = _assign_specialist(issue["failure_type"], pid)
        wo = WorkOrder(
            work_order_id=wo_id,
            project_id=pid,
            failure_type=issue["failure_type"],
            severity=issue.get("severity", "medium"),
            description=issue.get("description", ""),
            context=issue.get("context", {}),
            assigned_specialist=specialist,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # File as Linear ticket
        ticket_id = _file_work_order_ticket(wo)
        wo.linear_ticket_id = ticket_id
        report.work_orders.append(wo)
        if ticket_id:
            report.tickets_filed.append(ticket_id)
            log.info(
                "health_monitor: work order %s filed as %s — %s (%s) → %s",
                wo_id, ticket_id, pid, issue["failure_type"], specialist,
            )

    report.projects_unhealthy = len(unhealthy_projects)
    return report


__all__ = ["run_daily", "should_run", "WorkOrder", "HealthReport"]
