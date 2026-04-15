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
