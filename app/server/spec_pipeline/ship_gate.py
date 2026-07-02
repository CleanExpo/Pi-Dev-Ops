"""Boundary and ship gates for machine spec pipeline."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.spec_pipeline.ship_gate")

FORBIDDEN_PATHS = (
    "app/server/config.py",
    "app/server/auth.py",
    "app/data/.password-hash",
    "app/data/.session-secret",
    "dashboard/middleware.ts",
    "dashboard/app/api/actions/",
    "supabase/seed.sql",
)

FORBIDDEN_PATTERNS = (
    re.compile(r"\.env"),
    re.compile(r"sk-ant-"),
    re.compile(r"lin_api_"),
    re.compile(r"SUPABASE_.*KEY"),
    re.compile(r"postgres://"),
)

MAX_FILES_DEFAULT = int(os.environ.get("TAO_SCOPE_MAX_FILES", "5"))


@dataclass
class BoundaryResult:
    tier: str  # ok, warn, blocked
    blocked_paths: list[str] = field(default_factory=list)
    file_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "blocked_paths": self.blocked_paths,
            "file_count": self.file_count,
            "reason": self.reason,
        }


def machine_ship_enabled() -> bool:
    return os.environ.get("TAO_MACHINE_SHIP_MODE", "0").strip() == "1"


def scan_proposal_boundary(proposal: str) -> BoundaryResult:
    """Scan proposal text for forbidden path mentions."""
    blocked: list[str] = []
    lower = proposal.lower()
    for p in FORBIDDEN_PATHS:
        if p.lower() in lower:
            blocked.append(p)
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(proposal):
            blocked.append(pat.pattern)
    if blocked:
        return BoundaryResult(tier="blocked", blocked_paths=blocked,
                              reason="proposal references forbidden paths/secrets")
    return BoundaryResult(tier="ok")


def scan_diff_boundary(workspace: str) -> BoundaryResult:
    """Scan git diff for forbidden paths and file count."""
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        files = [f for f in (proc.stdout or "").splitlines() if f.strip()]
    except (subprocess.SubprocessError, OSError):
        return BoundaryResult(tier="warn", reason="could not read git diff")

    blocked = [f for f in files if any(f.startswith(p) or p in f for p in FORBIDDEN_PATHS)]
    if blocked:
        return BoundaryResult(tier="blocked", blocked_paths=blocked, file_count=len(files))
    tier = "warn" if len(files) > MAX_FILES_DEFAULT else "ok"
    return BoundaryResult(tier=tier, file_count=len(files))


def run_oracles(workspace: str) -> dict[str, bool]:
    """Run pytest + import check; tsc if dashboard touched."""
    results: dict[str, bool] = {"import_ok": False, "pytest_ok": False, "tsc_ok": True}
    try:
        proc = subprocess.run(
            ["python", "-c", "from app.server.main import app"],
            cwd=workspace, capture_output=True, text=True, timeout=60, check=False,
            env={**os.environ, "PYTHONPATH": workspace},
        )
        results["import_ok"] = proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        results["import_ok"] = False

    tests = Path(workspace) / "tests"
    if tests.is_dir():
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-x", "-q"],
                cwd=workspace, capture_output=True, text=True, timeout=300, check=False,
                env={**os.environ, "PYTHONPATH": workspace},
            )
            results["pytest_ok"] = proc.returncode == 0
        except (subprocess.SubprocessError, OSError):
            results["pytest_ok"] = False
    else:
        results["pytest_ok"] = True

    dash = Path(workspace) / "dashboard"
    touched = any(str(p).startswith("dashboard/") for p in _changed_files(workspace))
    if dash.is_dir() and touched:
        try:
            proc = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                cwd=str(dash), capture_output=True, text=True, timeout=180, check=False,
            )
            results["tsc_ok"] = proc.returncode == 0
        except (subprocess.SubprocessError, OSError):
            results["tsc_ok"] = False
    return results


def _changed_files(workspace: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except (subprocess.SubprocessError, OSError):
        return []


def _github_request(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Pi-CEO-SpecPipeline/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def open_pr_and_merge(
    *,
    repo: str,
    branch: str,
    title: str,
    body: str,
    poll_seconds: int = 30,
    max_polls: int = 40,
) -> dict[str, Any]:
    """Open PR and merge when checks green. Requires machine ship mode."""
    if not machine_ship_enabled():
        return {"status": "skipped", "reason": "TAO_MACHINE_SHIP_MODE off"}

    pr = _github_request("POST", f"/repos/{repo}/pulls", {
        "title": title,
        "head": branch,
        "base": "main",
        "body": body,
    })
    pr_number = pr.get("number")
    pr_url = pr.get("html_url", "")
    if not pr_number:
        return {"status": "error", "reason": "pr create failed", "raw": pr}

    import time
    for _ in range(max_polls):
        detail = _github_request("GET", f"/repos/{repo}/pulls/{pr_number}")
        head_sha = (detail.get("head") or {}).get("sha", "")
        checks = _github_request(
            "GET", f"/repos/{repo}/commits/{head_sha}/check-runs?per_page=100",
        )
        runs = checks.get("check_runs") or []
        if not runs:
            time.sleep(poll_seconds)
            continue
        required = [r for r in runs if r.get("status") == "completed"]
        if len(required) < len(runs):
            time.sleep(poll_seconds)
            continue
        if any(r.get("conclusion") not in ("success", "skipped", "neutral") for r in required):
            return {"status": "blocked", "pr_url": pr_url, "checks": runs}
        break
    else:
        return {"status": "timeout", "pr_url": pr_url}

    merge = _github_request(
        "PUT", f"/repos/{repo}/pulls/{pr_number}/merge",
        {"merge_method": "merge"},
    )
    return {
        "status": "merged" if merge.get("merged") else "merge_failed",
        "pr_url": pr_url,
        "merge_sha": merge.get("sha"),
    }
