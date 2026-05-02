"""swarm/providers/github_actions.py — real CTO platform provider.

Pulls real DORA metrics from GitHub Actions for each repo in
``.harness/projects.json``. Vercel + Datadog connectors land as follow-up
tickets — for now this connector handles the GitHub-side DORA quartet
(deploy frequency, lead time p50, MTTR, change-failure rate) and falls
back to synthetic for p99 latency, uptime, and cost-per-request.

Activate with::

    TAO_CTO_PROVIDER=github_actions

Required env:
* ``GITHUB_TOKEN`` — already in Pi-CEO env for the autonomous-PR loop.
  Read scope only: ``repo`` for private repos.

Per-business `.harness/projects.json` ``repo`` field is used as
``owner/name`` — already present for every business. The connector
queries the most recent 30 days of workflow runs on the default branch.

Safety:
* httpx timeout 8.0 s per call
* Read scope only — `gh api repos/:owner/:repo/actions/workflow_runs`
* Per-business try/except — one bad business never breaks the cycle
* Falls back to synthetic_platform_one(bid) on any failure
* httpx imported lazily — synthetic-only environments still load module

DORA computation:
* deploys_last_week = count of successful runs on default branch in last 7 days
* lead_time_hours_p50 = median (created_at → updated_at) over those runs
* mttr_hours = median (failure_run.created_at → next_success.updated_at)
* change_failure_count / change_total_count = last 30 days
"""
from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from ..cto import RawPlatformMetrics
from .synthetic import _load_business_ids
from .synthetic_platform import synthetic_platform_one

log = logging.getLogger("swarm.providers.github_actions")

GH_API_BASE = "https://api.github.com"
HTTP_TIMEOUT_S = 8.0
LOOKBACK_DAYS = 30
DEPLOY_WINDOW_DAYS = 7


def _gh_get(path: str, *, token: str,
             params: dict[str, Any] | None = None) -> dict[str, Any]:
    """One GitHub API GET. Raises on HTTP error so caller can fall back.

    httpx imported here so this module loads in environments without httpx.
    """
    import httpx  # noqa: PLC0415

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.get(f"{GH_API_BASE}{path}",
                       headers=headers, params=params)
        r.raise_for_status()
        return r.json()


def _parse_iso(ts: str) -> datetime | None:
    try:
        # GitHub returns 'Z' suffix; Python 3.11 isoformat parses it
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _runs_for_repo(repo: str, *, token: str
                    ) -> list[dict[str, Any]]:
    """Fetch workflow runs from the last LOOKBACK_DAYS for a repo."""
    since = (datetime.now(timezone.utc)
             - timedelta(days=LOOKBACK_DAYS)).isoformat()
    # GitHub's workflow_runs endpoint accepts a `created` query param.
    params = {
        "branch": "main",
        "per_page": 100,
        "created": f">={since[:10]}",
    }
    out = _gh_get(
        f"/repos/{repo}/actions/runs",
        token=token, params=params,
    )
    return list(out.get("workflow_runs") or [])


def _compute_dora(runs: list[dict[str, Any]]
                   ) -> dict[str, Any] | None:
    """Compute the DORA quartet from a list of workflow run dicts.

    Returns a dict suitable for splatting into RawPlatformMetrics, or
    None when there's not enough signal (no runs at all).
    """
    if not runs:
        return None

    now = datetime.now(timezone.utc)
    cutoff_deploy = now - timedelta(days=DEPLOY_WINDOW_DAYS)

    # Successful runs in last 7 days = deploys_last_week
    successes = [
        r for r in runs
        if (r.get("conclusion") == "success"
            and (_parse_iso(r.get("created_at") or "") or now) >= cutoff_deploy)
    ]
    deploys_last_week = len(successes)

    # Lead time p50 — created_at → updated_at across successful runs
    lead_times = []
    for r in successes:
        ca = _parse_iso(r.get("created_at") or "")
        ua = _parse_iso(r.get("updated_at") or "")
        if ca and ua:
            secs = (ua - ca).total_seconds()
            if secs >= 0:
                lead_times.append(secs / 3600.0)
    lead_time_hours_p50 = (
        statistics.median(lead_times) if lead_times else 0.0
    )

    # CFR over the full 30-day window
    total = [r for r in runs if r.get("status") == "completed"]
    failures = [r for r in total if r.get("conclusion") == "failure"]
    change_total_count = max(1, len(total))
    change_failure_count = len(failures)

    # MTTR — pair each failure with the next success on the same branch
    runs_chrono = sorted(
        [r for r in runs if r.get("status") == "completed"],
        key=lambda r: _parse_iso(r.get("created_at") or "") or now,
    )
    recovery_hours: list[float] = []
    for i, run in enumerate(runs_chrono):
        if run.get("conclusion") != "failure":
            continue
        for follow in runs_chrono[i + 1:]:
            if follow.get("conclusion") == "success":
                fc = _parse_iso(run.get("created_at") or "")
                fs = _parse_iso(follow.get("updated_at") or "")
                if fc and fs:
                    secs = (fs - fc).total_seconds()
                    if secs >= 0:
                        recovery_hours.append(secs / 3600.0)
                break
    mttr_hours = statistics.median(recovery_hours) if recovery_hours else 0.0

    return {
        "deploys_last_week": deploys_last_week,
        "lead_time_hours_p50": round(lead_time_hours_p50, 2),
        "mttr_hours": round(mttr_hours, 2),
        "change_failure_count": change_failure_count,
        "change_total_count": change_total_count,
    }


def _load_repo_for_business(bid: str) -> str | None:
    """Lookup the GitHub repo for a business id from .harness/projects.json."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / ".harness/projects.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    for proj in data.get("projects", []) or []:
        if proj.get("id") == bid:
            return proj.get("repo")
    return None


def _real_for_business(bid: str, *, token: str
                         ) -> RawPlatformMetrics | None:
    """Build RawPlatformMetrics for one business from GitHub Actions.

    Today: DORA quartet is real (when GitHub returns runs). p99 latency,
    uptime, cost-per-request stay synthetic until Vercel + Datadog
    connectors land.
    """
    repo = _load_repo_for_business(bid)
    if not repo:
        log.debug("github_actions: %s has no repo in projects.json", bid)
        return None

    try:
        runs = _runs_for_repo(repo, token=token)
    except Exception as exc:  # noqa: BLE001
        log.warning("github_actions: %s runs fetch failed (%s)", bid, exc)
        return None

    dora = _compute_dora(runs)
    if dora is None:
        log.debug("github_actions: %s no runs in lookback window", bid)
        return None

    base = synthetic_platform_one(bid)
    base.deploys_last_week = dora["deploys_last_week"]
    base.lead_time_hours_p50 = dora["lead_time_hours_p50"]
    base.mttr_hours = dora["mttr_hours"]
    base.change_failure_count = dora["change_failure_count"]
    base.change_total_count = dora["change_total_count"]
    return base


def github_actions_provider() -> list[RawPlatformMetrics]:
    """Real-data provider with per-business synthetic fallback."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        log.warning(
            "github_actions: GITHUB_TOKEN missing — emitting synthetic only"
        )
        return [synthetic_platform_one(b) for b in _load_business_ids()]

    out: list[RawPlatformMetrics] = []
    for bid in _load_business_ids():
        real = _real_for_business(bid, token=token)
        out.append(real if real is not None else synthetic_platform_one(bid))
    log.debug("github_actions: emitted %d metrics", len(out))
    return out


__all__ = ["github_actions_provider"]
