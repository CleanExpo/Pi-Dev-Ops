"""
pi_seo_monitor.py — Pi-SEO Monitor Agent (RA-541)

Intelligence layer over the Pi-SEO scanner. Reads scan history, detects
regressions, identifies systemic cross-repo patterns, generates remediation
guidance, and routes critical alerts through TriageEngine.

Dual mode:
  Local (no ANTHROPIC_API_KEY): deltas, regressions, portfolio scoring, alerts.
  Agent (ANTHROPIC_API_KEY set): adds AI remediation analysis and prose digest.

Usage:
    python -m app.server.agents.pi_seo_monitor [--project ID] [--dry-run] [--use-agent]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.agents.pi-seo-monitor")

# ─── paths ────────────────────────────────────────────────────────────────────

_HARNESS = Path(__file__).parent.parent.parent.parent / ".harness"
_RESULTS_ROOT = _HARNESS / "scan-results"
_DIGESTS_ROOT = _HARNESS / "monitor-digests"
_PROJECTS_FILE = _HARNESS / "projects.json"
_DIGEST_RETENTION_DAYS = 30

# ─── data model ───────────────────────────────────────────────────────────────

_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_REGRESSION_THRESHOLD = 5
_CRITICAL_REGRESSION_THRESHOLD = 15
_DEGRADATION_THRESHOLD = 70
_DEGRADATION_CONSECUTIVE = 3


@dataclass
class MonitorDigest:
    timestamp: str
    portfolio_health: int
    portfolio_delta: int
    project_scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    deltas: list[dict[str, Any]] = field(default_factory=list)
    regressions: list[dict[str, Any]] = field(default_factory=list)
    systemic_issues: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    remediation_cards: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    digest_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── project config ───────────────────────────────────────────────────────────

def _load_projects() -> list[dict[str, Any]]:
    """Load all projects from .harness/projects.json."""
    if not _PROJECTS_FILE.exists():
        return []
    with open(_PROJECTS_FILE) as f:
        data = json.load(f)
    return data.get("projects", [])


def _project_weight(project: dict[str, Any]) -> int:
    return _PRIORITY_WEIGHT.get(project.get("scan_priority", "medium"), 2)


# ─── scan result loading ──────────────────────────────────────────────────────

def _load_scan_results(project_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Load scan result JSON files from .harness/scan-results/.
    Returns { project_id: [result_dict, ...] } sorted newest-first.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    if not _RESULTS_ROOT.exists():
        return results

    dirs = (
        [_RESULTS_ROOT / project_id] if project_id else
        [d for d in _RESULTS_ROOT.iterdir() if d.is_dir()]
    )
    for project_dir in dirs:
        if not project_dir.is_dir():
            continue
        pid = project_dir.name
        files = sorted(project_dir.glob("*.json"), key=lambda p: p.name, reverse=True)
        scans = []
        for fp in files[:10]:  # last 10 per project for trend analysis
            try:
                with open(fp) as f:
                    scans.append(json.load(f))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Skipping malformed scan result %s: %s", fp, exc)
        if scans:
            results[pid] = scans
    return results


# ─── digest loading + pruning ─────────────────────────────────────────────────

def _load_previous_digest() -> dict[str, Any] | None:
    """Return the most recent saved digest, or None."""
    if not _DIGESTS_ROOT.exists():
        return None
    files = sorted(_DIGESTS_ROOT.glob("*.json"), key=lambda p: p.name, reverse=True)
    if not files:
        return None
    try:
        with open(files[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_digest(digest: MonitorDigest) -> Path:
    """Save digest to .harness/monitor-digests/{YYYYMMDD-HHMM}.json."""
    _DIGESTS_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    path = _DIGESTS_ROOT / f"{ts}.json"
    with open(path, "w") as f:
        json.dump(digest.to_dict(), f, indent=2)
    log.info("Digest saved: %s", path)
    return path


def _prune_old_digests() -> None:
    """Remove digest files older than DIGEST_RETENTION_DAYS."""
    if not _DIGESTS_ROOT.exists():
        return
    cutoff = datetime.now(timezone.utc).timestamp() - (_DIGEST_RETENTION_DAYS * 86400)
    for fp in _DIGESTS_ROOT.glob("*.json"):
        if fp.stat().st_mtime < cutoff:
            fp.unlink()
            log.info("Pruned old digest: %s", fp.name)


# ─── health score computation ─────────────────────────────────────────────────

def _project_health_score(scans: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute per-type and overall health score from the most recent scans.
    One JSON file per scan_type — use the newest file for each type.
    """
    by_type: dict[str, int] = {}
    latest_overall = 100

    for scan in scans:
        stype = scan.get("scan_type", "unknown")
        score = scan.get("health_score", 100)
        if stype not in by_type:
            by_type[stype] = score

    if by_type:
        latest_overall = int(sum(by_type.values()) / len(by_type))

    return {"overall": latest_overall, "by_type": by_type}


def _compute_deltas(
    current: dict[str, dict[str, Any]],
    previous_digest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Compare current project scores to previous digest."""
    if not previous_digest:
        return []
    prev_scores = previous_digest.get("project_scores", {})
    deltas = []
    for pid, info in current.items():
        prev = prev_scores.get(pid, {}).get("overall")
        if prev is None:
            continue
        delta = info["overall"] - prev
        deltas.append({"project_id": pid, "previous": prev, "current": info["overall"], "delta": delta})
    return deltas


# ─── regression + systemic detection ─────────────────────────────────────────

def _detect_regressions(
    deltas: list[dict[str, Any]],
    current_scans: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Identify projects with significant score drops or sustained degradation."""
    regressions = []

    for d in deltas:
        if d["delta"] <= -_CRITICAL_REGRESSION_THRESHOLD:
            regressions.append({**d, "severity": "critical", "type": "critical_regression"})
        elif d["delta"] <= -_REGRESSION_THRESHOLD:
            regressions.append({**d, "severity": "high", "type": "regression"})

    # Sustained degradation — below threshold for 3+ consecutive overall scores
    for pid, scans in current_scans.items():
        if len(scans) < _DEGRADATION_CONSECUTIVE:
            continue
        # Build overall score per scan (newest first)
        seen_types: dict[str, int] = {}
        cycle_scores = []
        for scan in scans:
            stype = scan.get("scan_type", "unknown")
            score = scan.get("health_score", 100)
            seen_types[stype] = score
            if len(seen_types) >= 2:
                cycle_scores.append(int(sum(seen_types.values()) / len(seen_types)))
                if len(cycle_scores) >= _DEGRADATION_CONSECUTIVE:
                    break

        if (
            len(cycle_scores) >= _DEGRADATION_CONSECUTIVE
            and all(s < _DEGRADATION_THRESHOLD for s in cycle_scores[:_DEGRADATION_CONSECUTIVE])
        ):
            if not any(r["project_id"] == pid for r in regressions):
                regressions.append({
                    "project_id": pid,
                    "type": "sustained_degradation",
                    "severity": "high",
                    "consecutive_scans_below_threshold": _DEGRADATION_CONSECUTIVE,
                    "threshold": _DEGRADATION_THRESHOLD,
                    "recent_scores": cycle_scores[:_DEGRADATION_CONSECUTIVE],
                })

    return regressions


def _detect_systemic_issues(
    all_scans: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Find findings with the same scan_type:title across 2+ repos."""
    key_to_projects: dict[str, set[str]] = {}

    for pid, scans in all_scans.items():
        for scan in scans[:1]:  # only latest per project
            for finding in scan.get("findings", []):
                key = f"{finding.get('scan_type', '')}:{finding.get('title', '')}"
                if key not in key_to_projects:
                    key_to_projects[key] = set()
                key_to_projects[key].add(pid)

    systemic = []
    for key, projects in key_to_projects.items():
        if len(projects) >= 2:
            stype, _, title = key.partition(":")
            systemic.append({
                "key": key,
                "scan_type": stype,
                "title": title,
                "affected_projects": sorted(projects),
                "count": len(projects),
            })

    return sorted(systemic, key=lambda x: x["count"], reverse=True)


# ─── RA-688: dependency zero-score detection ──────────────────────────────────

_DEPENDENCY_SCAN_TYPES = frozenset(["dependency", "dependencies", "npm_audit", "pip_audit"])
_DEP_ZERO_CONSECUTIVE = 2   # flag after this many consecutive zero-score dep scans


def _detect_dependency_zeros(
    all_scans: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """RA-688 — Find repos with dependency scan score == 0 for N+ consecutive scans.

    Returns a list of alert dicts for repos stuck at 0/100 on dependency health.
    These are separate from the general sustained-degradation check because:
    - 0/100 means the repo has known critical/high vulnerabilities that have
      been ignored for at least N scan cycles.
    - They should be flagged more aggressively than general degradation.
    """
    stuck_repos: list[dict[str, Any]] = []

    for pid, scans in all_scans.items():
        dep_scores: list[int] = []
        for scan in scans:
            if scan.get("scan_type", "").lower() in _DEPENDENCY_SCAN_TYPES:
                dep_scores.append(scan.get("health_score", 100))
            if len(dep_scores) >= _DEP_ZERO_CONSECUTIVE:
                break

        if len(dep_scores) >= _DEP_ZERO_CONSECUTIVE and all(
            s == 0 for s in dep_scores[:_DEP_ZERO_CONSECUTIVE]
        ):
            # Count total scans at 0 (may be more than the minimum threshold)
            total_zero = sum(1 for s in dep_scores if s == 0)
            stuck_repos.append({
                "project_id": pid,
                "type": "dependency_zero",
                "severity": "high",
                "consecutive_zero_scans": total_zero,
            })

    return stuck_repos


# ─── alert generation ─────────────────────────────────────────────────────────

def _generate_alerts(
    regressions: list[dict[str, Any]],
    systemic: list[dict[str, Any]],
    current_scans: dict[str, list[dict[str, Any]]],
    portfolio_health: int,
    portfolio_delta: int,
    dep_zeros: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the alerts list from regressions, systemic issues, and portfolio state."""
    alerts = []

    for r in regressions:
        if r["type"] == "critical_regression":
            alerts.append({
                "type": "regression_critical",
                "project_id": r["project_id"],
                "message": f"Score dropped {abs(r['delta'])} pts ({r['previous']} → {r['current']})",
                "severity": "critical",
            })
        elif r["type"] == "regression":
            alerts.append({
                "type": "regression",
                "project_id": r["project_id"],
                "message": f"Score dropped {abs(r['delta'])} pts ({r['previous']} → {r['current']})",
                "severity": "high",
            })
        elif r["type"] == "sustained_degradation":
            alerts.append({
                "type": "sustained_degradation",
                "project_id": r["project_id"],
                "message": f"Below {r['threshold']} for {r['consecutive_scans_below_threshold']}+ scans",
                "severity": "high",
            })

    # RA-688 — Repos stuck at 0/100 dependency score for 2+ consecutive scans
    for dep in (dep_zeros or []):
        pid = dep["project_id"]
        n = dep["consecutive_zero_scans"]
        alerts.append({
            "type": "dependency_zero",
            "project_id": pid,
            "message": (
                f"Dependency score 0/100 for {n} consecutive scans — "
                "known vulnerabilities ignored. Run `npm audit fix` or `pip-audit --fix`."
            ),
            "severity": "high",
        })

    # New critical findings
    for pid, scans in current_scans.items():
        for scan in scans[:1]:
            for finding in scan.get("findings", []):
                if finding.get("severity") == "critical":
                    alerts.append({
                        "type": "new_critical",
                        "project_id": pid,
                        "message": f"{finding.get('title', 'Unknown')} ({finding.get('scan_type', '')})",
                        "severity": "critical",
                    })

    # Deployment health failures
    for pid, scans in current_scans.items():
        for scan in scans[:1]:
            if scan.get("scan_type") == "deployment_health" and scan.get("error"):
                alerts.append({
                    "type": "deployment_down",
                    "project_id": pid,
                    "message": scan["error"][:200],
                    "severity": "critical",
                })

    for s in systemic:
        alerts.append({
            "type": "systemic",
            "project_id": "portfolio",
            "message": f"'{s['title']}' in {s['count']} repos: {', '.join(s['affected_projects'])}",
            "severity": "medium",
        })

    if portfolio_health < 75 and portfolio_delta < 0:
        alerts.append({
            "type": "portfolio_warning",
            "project_id": "portfolio",
            "message": f"Portfolio health at {portfolio_health} (delta {portfolio_delta:+d})",
            "severity": "medium",
        })

    return alerts


# ─── digest markdown ──────────────────────────────────────────────────────────

def _render_digest_markdown(digest: MonitorDigest) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Pi-SEO Health Digest — {now}",
        "",
        f"**Portfolio Health: {digest.portfolio_health}/100** ({digest.portfolio_delta:+d} vs previous)",
        "",
    ]

    critical_alerts = [a for a in digest.alerts if a["severity"] == "critical"]
    high_alerts = [a for a in digest.alerts if a["severity"] == "high"]

    if digest.alerts:
        lines.append(f"## Alerts ({len(digest.alerts)})")
        for a in critical_alerts:
            lines.append(f"- 🔴 CRITICAL [{a['project_id']}]: {a['message']}")
        for a in high_alerts:
            lines.append(f"- 🟡 HIGH [{a['project_id']}]: {a['message']}")
        for a in digest.alerts:
            if a["severity"] not in ("critical", "high"):
                lines.append(f"- 🔵 {a['severity'].upper()} [{a['project_id']}]: {a['message']}")
        lines.append("")

    if digest.project_scores:
        lines.append("## Project Scores")
        lines.append("| Project | Score | Delta | Trend |")
        lines.append("|---------|-------|-------|-------|")
        for pid, info in sorted(digest.project_scores.items()):
            delta = info.get("delta", 0)
            trend = "↑ improving" if delta > 2 else "↓ declining" if delta < -2 else "→ stable"
            lines.append(f"| {pid} | {info['overall']} | {delta:+d} | {trend} |")
        lines.append("")

    if digest.systemic_issues:
        lines.append(f"## Systemic Issues ({len(digest.systemic_issues)})")
        for s in digest.systemic_issues:
            lines.append(f"- `{s['key']}` — {s['count']} repos: {', '.join(s['affected_projects'])}")
        lines.append("")

    if digest.recommendations:
        lines.append("## Recommended Actions")
        for i, r in enumerate(digest.recommendations, 1):
            lines.append(f"{i}. {r}")

    return "\n".join(lines)


# ─── triage routing ───────────────────────────────────────────────────────────

def _route_critical_alerts(
    alerts: list[dict[str, Any]],
    all_scans: dict[str, list[dict[str, Any]]],
    projects: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    """Route critical alerts through TriageEngine."""
    critical = [a for a in alerts if a["severity"] == "critical"]
    if not critical:
        return

    linear_key = os.environ.get("LINEAR_API_KEY")
    if not linear_key:
        log.warning("LINEAR_API_KEY not set — skipping ticket creation for %d alerts", len(critical))
        return

    try:
        from app.server.triage import TriageEngine
        from app.server.scanner import Finding, ScanResult
    except ImportError as exc:
        log.error("Cannot import TriageEngine: %s", exc)
        return

    engine = TriageEngine()
    proj_map = {p["id"]: p for p in projects}

    for alert in critical:
        pid = alert["project_id"]
        if pid == "portfolio":
            pid = projects[0]["id"] if projects else None
        if not pid or pid not in proj_map:
            continue

        # Build a synthetic ScanResult with one finding for the alert
        finding = Finding(
            scan_type="monitor",
            severity="critical",
            title=f"[Monitor Alert] {alert['type']}: {alert['message'][:120]}",
            description=alert["message"],
        )
        result = ScanResult(
            project_id=pid,
            repo=proj_map[pid].get("repo", pid),
            scan_type="monitor",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            findings=[finding],
        )
        if dry_run:
            log.info("[dry-run] Would triage: %s — %s", pid, alert["message"])
        else:
            engine.triage(pid, [result])
            log.info("Triaged critical alert for %s", pid)


# ─── agent mode (AI remediation analysis) ────────────────────────────────────

_MONITOR_SYSTEM = """You are a Pi-SEO Portfolio Health Analyst. You receive scan results and a computed health digest, and you:

1. Identify the most critical remediation priorities across the portfolio
2. Produce remediation cards for Tier 2-4 findings (config changes, code refactors, architectural)
3. Write 3-5 actionable recommendations in priority order
4. Flag any patterns that local computation might have missed

Output JSON only:
{
  "remediation_cards": [...],
  "recommendations": ["...", "..."],
  "additional_observations": "string"
}
"""


def _run_agent_analysis(
    digest: MonitorDigest,
    all_scans: dict[str, list[dict[str, Any]]],
) -> None:
    """Run agent mode AI analysis and mutate digest in place."""
    try:
        from anthropic import Anthropic
    except ImportError:
        log.warning("anthropic package not available — skipping agent analysis")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return

    client = Anthropic(api_key=api_key)

    # Build a compact findings summary to stay within context limits
    findings_summary = []
    for pid, scans in all_scans.items():
        for scan in scans[:1]:
            for f in scan.get("findings", [])[:20]:
                if f.get("severity") in ("critical", "high", "medium"):
                    findings_summary.append({
                        "project": pid,
                        "scan_type": f.get("scan_type"),
                        "severity": f.get("severity"),
                        "title": f.get("title"),
                        "file_path": f.get("file_path"),
                        "auto_fixable": f.get("auto_fixable", False),
                    })

    prompt = json.dumps({
        "portfolio_health": digest.portfolio_health,
        "alerts": digest.alerts[:10],
        "regressions": digest.regressions[:5],
        "systemic_issues": digest.systemic_issues[:5],
        "top_findings": findings_summary[:30],
    }, indent=2)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=_MONITOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code block if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(text)
        digest.remediation_cards = data.get("remediation_cards", [])
        digest.recommendations = data.get("recommendations", [])
        obs = data.get("additional_observations", "")
        if obs:
            digest.digest_markdown += f"\n\n## AI Observations\n{obs}"
        log.info("Agent analysis complete: %d cards, %d recommendations",
                 len(digest.remediation_cards), len(digest.recommendations))
    except Exception as exc:
        log.error("Agent analysis failed: %s", exc)


# ─── main cycle ───────────────────────────────────────────────────────────────

def run_monitor_cycle(
    project_id: str | None = None,
    use_agent: bool = False,
    dry_run: bool = False,
) -> MonitorDigest:
    """
    Run one full monitor cycle:
      1. Load scan results
      2. Compute deltas vs previous digest
      3. Detect regressions + systemic issues
      4. Build alerts
      5. Optionally run agent analysis
      6. Save digest (unless dry_run)
      7. Prune old digests
    """
    log.info("Monitor cycle start — project=%s use_agent=%s dry_run=%s", project_id, use_agent, dry_run)

    projects = _load_projects()
    all_scans = _load_scan_results(project_id)
    previous = _load_previous_digest()

    # Project health scores
    project_scores: dict[str, dict[str, Any]] = {}
    for pid, scans in all_scans.items():
        project_scores[pid] = _project_health_score(scans)

    # Deltas
    deltas = _compute_deltas(project_scores, previous)
    delta_map = {d["project_id"]: d["delta"] for d in deltas}
    for pid, info in project_scores.items():
        info["delta"] = delta_map.get(pid, 0)
        info["trend"] = (
            "improving" if info["delta"] > 2
            else "declining" if info["delta"] < -2
            else "stable"
        )

    # Portfolio health (weighted average)
    proj_map = {p["id"]: p for p in projects}
    total_weight = 0
    weighted_sum = 0
    for pid, info in project_scores.items():
        w = _project_weight(proj_map.get(pid, {}))
        weighted_sum += info["overall"] * w
        total_weight += w
    portfolio_health = int(weighted_sum / total_weight) if total_weight else 0

    prev_portfolio = previous.get("portfolio_health", portfolio_health) if previous else portfolio_health
    portfolio_delta = portfolio_health - prev_portfolio

    # Regressions + systemic issues + RA-688 dependency zeros
    regressions = _detect_regressions(deltas, all_scans)
    systemic = _detect_systemic_issues(all_scans)
    dep_zeros = _detect_dependency_zeros(all_scans)
    alerts = _generate_alerts(
        regressions, systemic, all_scans, portfolio_health, portfolio_delta,
        dep_zeros=dep_zeros,
    )

    # Basic recommendations (overwritten by agent if use_agent)
    recommendations = []
    critical_alerts = [a for a in alerts if a["severity"] == "critical"]
    if critical_alerts:
        recommendations.append(f"Address {len(critical_alerts)} critical alert(s) immediately")
    if regressions:
        worst = min(regressions, key=lambda r: r.get("delta", 0), default=None)
        if worst:
            recommendations.append(f"Investigate regression in {worst.get('project_id')} ({worst.get('delta', 0):+d} pts)")
    if systemic:
        recommendations.append(f"Fix systemic issue affecting {systemic[0]['count']} repos: {systemic[0]['title']}")

    digest = MonitorDigest(
        timestamp=datetime.now(timezone.utc).isoformat(),
        portfolio_health=portfolio_health,
        portfolio_delta=portfolio_delta,
        project_scores=project_scores,
        deltas=deltas,
        regressions=regressions,
        systemic_issues=systemic,
        alerts=alerts,
        recommendations=recommendations,
    )

    # Agent analysis (AI layer)
    if use_agent:
        _run_agent_analysis(digest, all_scans)

    # Render markdown digest
    digest.digest_markdown = _render_digest_markdown(digest)

    # Route critical alerts through TriageEngine
    _route_critical_alerts(alerts, all_scans, projects, dry_run)

    if not dry_run:
        _save_digest(digest)
        _prune_old_digests()
    else:
        log.info("[dry-run] Digest not saved. Portfolio health: %d (%+d)", portfolio_health, portfolio_delta)
        log.info("[dry-run] Alerts: %d, Regressions: %d, Systemic: %d",
                 len(alerts), len(regressions), len(systemic))

    log.info("Monitor cycle complete — health=%d delta=%+d alerts=%d",
             portfolio_health, portfolio_delta, len(alerts))
    return digest


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    parser = argparse.ArgumentParser(description="Pi-SEO Monitor Agent")
    parser.add_argument("--project", help="Scope to a single project ID")
    parser.add_argument("--dry-run", action="store_true", help="Skip ticket creation and digest save")
    parser.add_argument("--use-agent", action="store_true", help="Enable AI remediation analysis")
    args = parser.parse_args()

    digest = run_monitor_cycle(
        project_id=args.project,
        use_agent=args.use_agent,
        dry_run=args.dry_run,
    )
    print(digest.digest_markdown)


if __name__ == "__main__":
    main()
