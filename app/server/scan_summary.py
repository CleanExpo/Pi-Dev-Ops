"""Per-project scan summary for ProjectScanner.get_health_summary.

The summary feeds the Mission Control project cards. Two rules keep a card honest:

- `finished_at` is the OLDEST finish time among the scans behind `overall_health`,
  so a score is only ever as fresh as its stalest input. Any undated input makes
  it None ("scan date unknown"), never a guess.
- `deploy_check` passes through the last deployment_health record the scanner
  already wrote. It makes no HTTP call. No record is None ("not tracked"); an
  unreadable record is an error, never "no issues".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCAN_TYPES = ("security", "code_quality", "dependencies", "deployment_health")
DEPLOY_SCAN = "deployment_health"
UNREADABLE = "deploy check record unreadable"

ScoreFn = Callable[[str, list[dict[str, Any]]], int]


def _latest(result_dir: Path, scan_type: str) -> Path | None:
    files = sorted(result_dir.glob(f"*-{scan_type}.json")) if result_dir.exists() else []
    return files[-1] if files else None


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("scan record unreadable %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def oldest_finished_at(records: list[dict[str, Any]]) -> str | None:
    """Oldest `finished_at` across records; None if empty or any record is undated."""
    stamps = [(_parse_time(r.get("finished_at")), r.get("finished_at")) for r in records]
    if not stamps or any(parsed is None for parsed, _ in stamps):
        return None
    return min(stamps, key=lambda pair: pair[0])[1]


def deploy_check(result_dir: Path) -> dict[str, Any] | None:
    """The last recorded deployment_health scan, or None when none was ever recorded."""
    path = _latest(result_dir, DEPLOY_SCAN)
    if path is None:
        return None
    data = _read(path)
    if data is None:
        return {"finished_at": None, "error": UNREADABLE, "findings": []}
    findings = data.get("findings") if isinstance(data.get("findings"), list) else []
    return {
        "finished_at": data.get("finished_at") if _parse_time(data.get("finished_at")) else None,
        "error": str(data.get("error") or ""),
        "findings": [
            {"severity": str(f.get("severity", "")), "title": str(f.get("title", ""))}
            for f in findings if isinstance(f, dict)
        ],
    }


def summarise_project(proj: dict[str, Any], result_dir: Path, score_of: ScoreFn) -> dict[str, Any]:
    """One summary row: scores, findings counts, scan date, deployments and deploy check."""
    scores: dict[str, int] = {}
    findings_count: dict[str, int] = {}
    used: list[dict[str, Any]] = []
    for scan_type in SCAN_TYPES:
        path = _latest(result_dir, scan_type)
        data = _read(path) if path else None
        if data is None:
            continue
        raw = data.get("findings", [])
        findings_count[scan_type] = len(raw)
        scores[scan_type] = score_of(scan_type, raw)
        used.append(data)
    return {
        "project_id": proj["id"],
        "repo": proj["repo"],
        "overall_health": int(sum(scores.values()) / len(scores)) if scores else 100,
        "scores": scores,
        "findings_count": findings_count,
        "deployments": proj.get("deployments", {}),
        "finished_at": oldest_finished_at(used),
        "deploy_check": deploy_check(result_dir),
    }
