"""
vercel_monitor.py — RA-692: Frontend deployment drift monitoring.

Polls the Vercel Deployments API to detect whether the frontend is
behind the latest main-branch commit. Exposes:

    get_latest_deployment()  → dict | None
    check_deployment_drift() → DriftResult

Called from GET /api/health/vercel (main.py).

When VERCEL_TOKEN is not set, all functions return degraded=True
immediately without making any network requests.
"""
from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from . import config

log = logging.getLogger("pi-ceo.vercel_monitor")

_VERCEL_API = "https://api.vercel.com"
_DEPLOYMENTS_TIMEOUT = 8  # seconds


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class DriftResult:
    degraded: bool                     # True when token/project not configured
    latest_deployment_sha: str         # Git SHA of most-recent prod deployment
    head_sha: str                       # Current HEAD of local main branch
    drifted: bool                       # True when head_sha != latest_deployment_sha
    deployment_state: str              # "READY" | "ERROR" | "BUILDING" | ""
    deployment_url: str                # Preview URL of the latest deployment
    error: Optional[str] = None        # Error message if API call failed


# ── API helpers ───────────────────────────────────────────────────────────────

def _vercel_get(path: str) -> dict:
    """Make a GET to the Vercel API. Raises on non-200."""
    url = f"{_VERCEL_API}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {config.VERCEL_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=_DEPLOYMENTS_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _build_deployments_url() -> str:
    """Build the deployments list URL, scoped by team and project when set."""
    params: list[str] = ["limit=5", "target=production"]
    if config.VERCEL_PROJECT_ID:
        params.append(f"projectId={config.VERCEL_PROJECT_ID}")
    if config.VERCEL_TEAM_ID:
        params.append(f"teamId={config.VERCEL_TEAM_ID}")
    return f"/v6/deployments?{'&'.join(params)}"


def get_latest_deployment() -> Optional[dict]:
    """Return the most-recent production deployment record, or None on failure."""
    if not config.VERCEL_TOKEN:
        return None
    try:
        data = _vercel_get(_build_deployments_url())
        deployments = data.get("deployments", [])
        return deployments[0] if deployments else None
    except Exception as exc:
        log.warning("vercel_monitor: API call failed: %s", exc)
        return None


def _local_head_sha() -> str:
    """Return the current HEAD SHA of the local repo (first 12 chars)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()[:12]
    except Exception:
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def check_deployment_drift() -> DriftResult:
    """Check whether the frontend deployment is behind HEAD.

    Returns DriftResult:
      degraded=True   when VERCEL_TOKEN is not configured
      drifted=True    when the deployed SHA differs from local HEAD
      drifted=False   when they match or when deployment SHA is unavailable
    """
    if not config.VERCEL_TOKEN:
        return DriftResult(
            degraded=True,
            latest_deployment_sha="",
            head_sha="",
            drifted=False,
            deployment_state="",
            deployment_url="",
            error="VERCEL_TOKEN not configured — set it in Railway env vars",
        )

    head = _local_head_sha()
    try:
        dep = get_latest_deployment()
    except Exception as exc:
        return DriftResult(
            degraded=True,
            latest_deployment_sha="",
            head_sha=head,
            drifted=False,
            deployment_state="",
            deployment_url="",
            error=str(exc),
        )

    if dep is None:
        return DriftResult(
            degraded=False,
            latest_deployment_sha="",
            head_sha=head,
            drifted=False,
            deployment_state="",
            deployment_url="",
            error="No production deployments found",
        )

    dep_sha = (dep.get("meta", {}) or {}).get("githubCommitSha", "")[:12]
    dep_state = dep.get("state", "")
    dep_url = dep.get("url", "")
    drifted = bool(head and dep_sha and head != dep_sha)

    if drifted:
        log.warning(
            "vercel_monitor: DRIFT DETECTED — head=%s deployed=%s state=%s",
            head, dep_sha, dep_state,
        )

    return DriftResult(
        degraded=False,
        latest_deployment_sha=dep_sha,
        head_sha=head,
        drifted=drifted,
        deployment_state=dep_state,
        deployment_url=dep_url,
    )
