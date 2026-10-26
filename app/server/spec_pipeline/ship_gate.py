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

from ..verification_sandbox import SandboxUnavailable, run_isolated

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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            return BoundaryResult(tier="blocked", reason="could not read git diff")
        files = [f for f in (proc.stdout or "").splitlines() if f.strip()]
    except (subprocess.SubprocessError, OSError):
        return BoundaryResult(tier="blocked", reason="could not read git diff")

    blocked = [f for f in files if any(f.startswith(p) or p in f for p in FORBIDDEN_PATHS)
               or any(part.startswith(".env") for part in Path(f).parts)
               or Path(f).suffix.lower() in {".key", ".pem"}]
    if blocked:
        return BoundaryResult(tier="blocked", blocked_paths=blocked, file_count=len(files))
    tier = "warn" if len(files) > MAX_FILES_DEFAULT else "ok"
    return BoundaryResult(tier=tier, file_count=len(files))


def run_oracles(workspace: str) -> dict[str, bool]:
    """Run pytest + import check; tsc if dashboard touched."""
    results: dict[str, bool] = {"import_ok": False, "pytest_ok": False, "tsc_ok": True}
    try:
        proc = run_isolated(
            workspace, ["python3", "-c", "from app.server.main import app"], timeout_s=60,
        )
        results["import_ok"] = proc.returncode == 0
    except (SandboxUnavailable, subprocess.SubprocessError, OSError):
        results["import_ok"] = False

    tests = Path(workspace) / "tests"
    if tests.is_dir():
        try:
            proc = run_isolated(
                workspace, ["python3", "-m", "pytest", "tests/", "-x", "-q"], timeout_s=300,
            )
            results["pytest_ok"] = proc.returncode == 0
        except (SandboxUnavailable, subprocess.SubprocessError, OSError):
            results["pytest_ok"] = False
    dash = Path(workspace) / "dashboard"
    try:
        touched = any(str(p).startswith("dashboard/") for p in _changed_files(workspace))
    except RuntimeError:
        results["tsc_ok"] = False
        return results
    if dash.is_dir() and touched:
        try:
            proc = run_isolated(
                workspace, ["npx", "--no-install", "tsc", "--noEmit"],
                cwd=str(dash), timeout_s=180,
            )
            results["tsc_ok"] = proc.returncode == 0
        except (SandboxUnavailable, subprocess.SubprocessError, OSError):
            results["tsc_ok"] = False
    return results


def _changed_files(workspace: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", workspace, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            raise RuntimeError("could not determine verification scope from git diff")
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError("could not determine verification scope from git diff") from exc


def _github_request(method: str, path: str, body: dict | None = None) -> dict | list:
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
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _wait_for_candidate_checks(repo, pr_number, pr_url, candidate_sha, poll_seconds, max_polls):
    import time
    from .github_required_checks import candidate_snapshot
    receipt = {"pr_url": pr_url, "candidate_sha": candidate_sha}
    try:
        for _ in range(max_polls):
            state, required = candidate_snapshot(_github_request, repo, pr_number, candidate_sha)
            if state == "failed":
                return {**receipt, "status": "blocked", "reason": "A required CI context did not succeed"}
            if state == "passed":
                final, final_required = candidate_snapshot(_github_request, repo, pr_number, candidate_sha)
                if final == "passed" and final_required == required:
                    return None
                if final == "failed" or final_required != required:
                    return {**receipt, "status": "blocked", "reason": "Required CI changed before merge"}
            time.sleep(poll_seconds)
    except (RuntimeError, OSError, ValueError) as exc:
        return {**receipt, "status": "blocked", "reason": f"CI verification unavailable: {type(exc).__name__}"}
    return {**receipt, "status": "timeout", "reason": "Required CI contexts are missing or pending"}


def open_pr_and_merge(
    *,
    repo: str,
    branch: str,
    title: str,
    body: str,
    candidate_sha: str,
    poll_seconds: int = 30,
    max_polls: int = 40,
) -> dict[str, Any]:
    """Open PR; require complete successful CI for the exact reviewed candidate."""
    if not machine_ship_enabled():
        return {"status": "skipped", "reason": "TAO_MACHINE_SHIP_MODE off"}
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", candidate_sha):
        return {"status": "blocked", "reason": "reviewed candidate SHA is required"}

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

    blocked = _wait_for_candidate_checks(repo, pr_number, pr_url, candidate_sha, poll_seconds, max_polls)
    if blocked is not None:
        return blocked

    merge = _github_request(
        "PUT", f"/repos/{repo}/pulls/{pr_number}/merge",
        {"merge_method": "merge", "sha": candidate_sha},
    )
    return {
        "status": "merged" if merge.get("merged") else "merge_failed",
        "pr_url": pr_url,
        "merge_sha": merge.get("sha"),
        "candidate_sha": candidate_sha,
    }
