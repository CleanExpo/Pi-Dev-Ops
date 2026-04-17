"""Scan and monitor routes: /api/scan, /api/projects/health, /api/monitor (RA-937)."""
import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_auth, require_rate_limit
from ..models import ScanRequest, MonitorRequest

log = logging.getLogger("pi-ceo.main")

router = APIRouter()

# RA-1018: keep strong references to fire-and-forget scan tasks so GC cannot
# collect them mid-run.  Keyed by repo_url (or "all" for portfolio scans).
_scan_tasks: dict[str, asyncio.Task] = {}


@router.post("/api/scan", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def trigger_scan(body: ScanRequest):
    """Trigger Pi-SEO autonomous scan for one or all projects."""
    from ..scanner import ProjectScanner
    from ..triage import TriageEngine

    project_id = body.project_id
    scan_types = [s for s in body.scan_types] if body.scan_types else None
    dry_run = body.dry_run

    scanner = ProjectScanner()
    engine = TriageEngine()

    async def _run() -> dict:
        if project_id:
            projects = scanner.load_projects()
            proj = next((p for p in projects if p["id"] == project_id), None)
            if not proj:
                return {"error": f"project_id '{project_id}' not found"}
            results = await scanner.scan_project(proj, scan_types)
            created = engine.triage(project_id, results, dry_run=dry_run)
            out: dict = {
                "project_id": project_id,
                "scan_results": [
                    {"scan_type": r.scan_type, "findings": len(r.findings), "health_score": r.health_score}
                    for r in results
                ],
                "tickets_created": len(created),
                "dry_run": dry_run,
            }
            if body.auto_pr:
                from ..autopr import run_autopr
                out["auto_pr"] = await run_autopr(proj, dry_run=dry_run)
            return out
        else:
            all_results = await scanner.scan_all(scan_types=scan_types)
            all_created = engine.triage_all(all_results, dry_run=dry_run)
            out = {
                "projects_scanned": len(all_results),
                "tickets_created": sum(len(v) for v in all_created.values()),
                "dry_run": dry_run,
                "summary": {
                    pid: {
                        "findings": sum(len(r.findings) for r in results),
                        "tickets": len(all_created.get(pid, [])),
                    }
                    for pid, results in all_results.items()
                },
            }
            if body.auto_pr:
                from ..autopr import run_autopr_all
                out["auto_pr"] = await run_autopr_all(dry_run=dry_run)
            return out

    task_key = body.project_id or "all"
    # RA-1018: store the Task so GC cannot collect it before completion.
    task = asyncio.create_task(_run())
    _scan_tasks[task_key] = task

    def _cleanup(t: asyncio.Task) -> None:
        _scan_tasks.pop(task_key, None)

    task.add_done_callback(_cleanup)
    return {"ok": True, "message": "Scan started — results will be saved to .harness/scan-results/"}


@router.get("/api/projects/health", dependencies=[Depends(require_auth)])
async def projects_health():
    """Return health scores for all projects based on latest scan results."""
    from ..scanner import ProjectScanner
    scanner = ProjectScanner()
    return scanner.get_health_summary()


# RA-1100: Portfolio Health drill-down — return per-project finding detail
# so the dashboard can show what's hurting the score and offer "fix it" actions.
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@router.get("/api/projects/{project_id}/findings", dependencies=[Depends(require_auth)])
async def project_findings(project_id: str, limit: int = 25):
    """Return top findings for a project, merged across the latest scan of every type.

    Sorted by severity (critical first) then alphabetically. `auto_fixable` flag
    surfaced so the frontend can offer the "Fix with Claude" button only where it
    makes sense.
    """
    import glob as _glob
    import re as _re

    # Sanitise project_id — only allow alnum + dash + underscore
    safe_id = _re.sub(r"[^a-zA-Z0-9_-]", "", project_id)
    if not safe_id:
        return {"error": "invalid project_id"}

    scan_root = Path(__file__).parent.parent.parent.parent / ".harness" / "scan-results" / safe_id
    if not scan_root.is_dir():
        return {"project_id": safe_id, "findings": [], "scans": [], "error": "no scan results"}

    # For each scan type, load the LATEST file by date prefix
    files_by_type: dict[str, str] = {}
    for f in sorted(_glob.glob(str(scan_root / "*.json")), reverse=True):
        # Filename: YYYY-MM-DD-<scan_type>.json
        name = Path(f).stem
        parts = name.split("-", 3)
        if len(parts) >= 4:
            scan_type = parts[3]
            if scan_type not in files_by_type:
                files_by_type[scan_type] = f

    findings: list[dict] = []
    scans: list[dict] = []
    for scan_type, fpath in files_by_type.items():
        try:
            with open(fpath) as f:
                data = json.load(f)
            scans.append({
                "scan_type": scan_type,
                "finished_at": data.get("finished_at"),
                "health_score": data.get("health_score"),
                "finding_count": len(data.get("findings", [])),
            })
            for finding in data.get("findings", []):
                # Trim noisy fields, keep what the UI needs
                findings.append({
                    "scan_type": finding.get("scan_type", scan_type),
                    "severity": finding.get("severity", "info"),
                    "title": finding.get("title", ""),
                    "description": (finding.get("description") or "")[:280],
                    "file_path": finding.get("file_path", ""),
                    "line_number": finding.get("line_number", 0) or None,
                    "auto_fixable": bool(finding.get("auto_fixable", False)),
                })
        except (json.JSONDecodeError, OSError) as exc:
            scans.append({"scan_type": scan_type, "error": str(exc)})

    # Sort: severity first, then title alpha
    findings.sort(key=lambda f: (_SEVERITY_RANK.get(f["severity"], 99), f["title"]))

    return {
        "project_id": safe_id,
        "scans": scans,
        "findings": findings[: max(1, min(int(limit), 200))],
        "truncated": len(findings) > limit,
        "total_findings": len(findings),
    }


@router.post("/api/monitor", dependencies=[Depends(require_auth)])
async def trigger_monitor(body: MonitorRequest, background_tasks: BackgroundTasks):
    """Run a Pi-SEO monitor cycle (portfolio health + regression detection)."""
    from ..agents.pi_seo_monitor import run_monitor_cycle

    async def _run():
        run_monitor_cycle(
            project_id=body.project_id,
            use_agent=body.use_agent,
            dry_run=body.dry_run,
        )

    background_tasks.add_task(_run)
    return {"ok": True, "dry_run": body.dry_run}


@router.get("/api/monitor/digest", dependencies=[Depends(require_auth)])
async def get_monitor_digest():
    """Return the latest monitor digest JSON."""
    import glob as _glob
    digests_root = Path(__file__).parent.parent.parent.parent / ".harness" / "monitor-digests"
    files = sorted(_glob.glob(str(digests_root / "*.json")), reverse=True)
    if not files:
        return {"error": "No monitor digest found"}
    try:
        with open(files[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}
