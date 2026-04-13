"""
autopr.py — Pi-SEO Auto-PR Generator (RA-537)

For each project with auto_fixable findings, this module:
  1. Reads the latest scan results from .harness/scan-results/
  2. Applies fixes per scan type:
       - dependencies/npm  → npm audit fix
       - dependencies/pip  → pip-audit --fix
       - code_quality/ruff → ruff check --fix
  3. Creates a branch `pi-seo/auto-fix-{date}` and commits the changes
  4. Opens a GitHub PR via the REST API

Requires: GITHUB_TOKEN env var with repo + pull-request write scopes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.autopr")

_HARNESS = Path(__file__).parent.parent.parent / ".harness"
_RESULTS_ROOT = _HARNESS / "scan-results"
_SCAN_WORKSPACE = Path(
    os.environ.get("SCAN_WORKSPACE_ROOT", str(Path.home() / "pi-seo-workspace"))
)
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_API = "https://api.github.com"


# ─── GitHub API client ────────────────────────────────────────────────────────


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{_GITHUB_API}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "Pi-SEO-AutoPR/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"GitHub API {method} {path} → {exc.code}: {body_text}") from exc

    def get_default_branch(self, repo: str) -> str:
        data = self._request("GET", f"/repos/{repo}")
        return data.get("default_branch", "main")

    def get_ref_sha(self, repo: str, ref: str) -> str:
        data = self._request("GET", f"/repos/{repo}/git/ref/heads/{ref}")
        return data["object"]["sha"]

    def create_ref(self, repo: str, branch: str, sha: str) -> None:
        self._request("POST", f"/repos/{repo}/git/refs", {
            "ref": f"refs/heads/{branch}",
            "sha": sha,
        })

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> str:
        data = self._request("POST", f"/repos/{repo}/pulls", {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        })
        return data["html_url"]


# ─── fix strategies ───────────────────────────────────────────────────────────


async def _apply_npm_fix(repo_path: Path) -> list[str]:
    """Run npm audit fix, return list of changed files."""
    proc = await asyncio.create_subprocess_exec(
        "npm", "audit", "fix",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        log.info("npm audit fix output: %s", stdout.decode("utf-8", errors="replace")[:200])
    except asyncio.TimeoutError:
        log.warning("npm audit fix timed out for %s", repo_path)
    return ["package.json", "package-lock.json"]


async def _apply_pip_fix(repo_path: Path) -> list[str]:
    """Run pip-audit --fix, return list of changed files."""
    proc = await asyncio.create_subprocess_exec(
        "pip-audit", "--fix", "--progress-spinner=off",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        log.warning("pip-audit --fix timed out for %s", repo_path)
    changed = []
    for fname in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        if (repo_path / fname).exists():
            changed.append(fname)
    return changed


async def _apply_ruff_fix(repo_path: Path) -> list[str]:
    """Run ruff check --fix, return list of changed Python files."""
    proc = await asyncio.create_subprocess_exec(
        "ruff", "check", ".", "--fix", "--output-format=json",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        data = json.loads(stdout or "[]")
        return list({item.get("filename", "") for item in data if item.get("filename")})
    except (asyncio.TimeoutError, json.JSONDecodeError):
        return []


# ─── git helpers ──────────────────────────────────────────────────────────────


async def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_AUTHOR_NAME": "Pi-SEO", "GIT_AUTHOR_EMAIL": "pi-seo@pi-ceo.internal"},
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    output = (stdout + stderr).decode("utf-8", errors="replace")
    return proc.returncode, output


async def _has_changes(repo_path: Path) -> bool:
    rc, out = await _git(["status", "--porcelain"], repo_path)
    return bool(out.strip())


# ─── load auto-fixable findings ───────────────────────────────────────────────


def _load_fixable_findings(project_id: str) -> dict[str, list[dict]]:
    """Return {scan_type: [findings]} for auto_fixable=True findings from latest scans."""
    result_dir = _RESULTS_ROOT / project_id
    if not result_dir.exists():
        return {}
    fixable: dict[str, list[dict]] = {}
    for scan_type in ("dependencies", "code_quality"):
        files = sorted(result_dir.glob(f"*-{scan_type}.json"))
        if not files:
            continue
        try:
            data = json.loads(files[-1].read_text())
        except (json.JSONDecodeError, OSError):
            continue
        hits = [f for f in data.get("findings", []) if f.get("auto_fixable")]
        if hits:
            fixable[scan_type] = hits
    return fixable


# ─── main entry point ─────────────────────────────────────────────────────────


async def run_autopr(
    project: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Apply auto-fixes for a single project and open a GitHub PR.

    Returns:
        {"project_id": ..., "pr_url": ..., "fixes_applied": [...], "skipped": bool}
    """
    pid = project["id"]
    repo = project["repo"]

    fixable = _load_fixable_findings(pid)
    if not fixable:
        log.info("No auto-fixable findings for %s", pid)
        return {"project_id": pid, "pr_url": None, "fixes_applied": [], "skipped": True}

    if not _GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — cannot create PR for %s", pid)
        return {"project_id": pid, "pr_url": None, "fixes_applied": [], "skipped": True}

    repo_name = repo.split("/")[-1]
    repo_path = _SCAN_WORKSPACE / repo_name

    if not repo_path.exists():
        log.warning("Repo not cloned: %s — run scanner first", repo_path)
        return {"project_id": pid, "pr_url": None, "fixes_applied": [], "skipped": True}

    branch = f"pi-seo/auto-fix-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
    rc, _ = await _git(["checkout", "-b", branch], repo_path)
    if rc != 0:
        # branch may already exist; try checkout
        await _git(["checkout", branch], repo_path)

    fixes_applied: list[str] = []

    # Apply fixes per scan type
    has_npm = any(f.get("file_path", "").startswith("package") for f in fixable.get("dependencies", []))
    has_pip = any(f.get("file_path", "").startswith("requirements") or f.get("file_path", "") == "pyproject.toml"
                  for f in fixable.get("dependencies", []))

    if has_npm and (repo_path / "package.json").exists():
        await _apply_npm_fix(repo_path)
        fixes_applied.append("npm audit fix")

    if has_pip and ((repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists()):
        await _apply_pip_fix(repo_path)
        fixes_applied.append("pip-audit --fix")

    if "code_quality" in fixable:
        changed = await _apply_ruff_fix(repo_path)
        if changed:
            fixes_applied.append(f"ruff --fix ({len(changed)} files)")

    if not await _has_changes(repo_path):
        log.info("No file changes after fixes for %s", pid)
        await _git(["checkout", "-"], repo_path)
        await _git(["branch", "-D", branch], repo_path)
        return {"project_id": pid, "pr_url": None, "fixes_applied": fixes_applied, "skipped": True}

    if dry_run:
        log.info("[dry-run] Would create PR for %s with: %s", pid, fixes_applied)
        await _git(["checkout", "-"], repo_path)
        await _git(["branch", "-D", branch], repo_path)
        return {"project_id": pid, "pr_url": None, "fixes_applied": fixes_applied, "skipped": False}

    # Commit and push
    await _git(["add", "-A"], repo_path)
    commit_msg = f"fix(pi-seo): auto-fix {len(fixes_applied)} findings\n\nApplied by Pi-SEO auto-PR generator.\nFixes: {', '.join(fixes_applied)}"
    await _git(["commit", "-m", commit_msg], repo_path)

    rc, out = await _git(
        ["push", f"https://x-access-token:{_GITHUB_TOKEN}@github.com/{repo}.git", branch],
        repo_path,
    )
    if rc != 0:
        log.error("git push failed for %s: %s", pid, out[:200])
        return {"project_id": pid, "pr_url": None, "fixes_applied": fixes_applied, "skipped": False}

    # Create PR
    gh = GitHubClient(_GITHUB_TOKEN)
    try:
        base_branch = gh.get_default_branch(repo)
        pr_body = _build_pr_body(pid, fixable, fixes_applied)
        pr_url = gh.create_pr(
            repo=repo,
            title=f"[Pi-SEO] Auto-fix: {len(fixes_applied)} fixable finding(s)",
            body=pr_body,
            head=branch,
            base=base_branch,
        )
        log.info("Created PR for %s: %s", pid, pr_url)
    except RuntimeError as exc:
        log.error("PR creation failed for %s: %s", pid, exc)
        pr_url = None

    # Return to default branch in workspace
    await _git(["checkout", base_branch], repo_path)

    return {"project_id": pid, "pr_url": pr_url, "fixes_applied": fixes_applied, "skipped": False}


def _build_pr_body(project_id: str, fixable: dict[str, list[dict]], fixes_applied: list[str]) -> str:
    lines = [
        "## Pi-SEO Auto-Fix",
        "",
        f"Automated fixes generated by the Pi-SEO scanner for project `{project_id}`.",
        "",
        "### Fixes Applied",
        "",
    ]
    for fix in fixes_applied:
        lines.append(f"- `{fix}`")
    lines += [
        "",
        "### Findings Addressed",
        "",
        "| Scan Type | Count | Severity |",
        "|-----------|-------|----------|",
    ]
    for scan_type, findings in fixable.items():
        severity = findings[0].get("severity", "—") if findings else "—"
        lines.append(f"| {scan_type} | {len(findings)} | {severity} |")
    lines += [
        "",
        "---",
        "*Generated by Pi-SEO autonomous scanner. Review before merging.*",
    ]
    return "\n".join(lines)


async def run_autopr_all(dry_run: bool = False) -> list[dict[str, Any]]:
    """Run auto-PR for all projects with auto-fixable findings."""
    projects_file = _HARNESS / "projects.json"
    with open(projects_file) as f:
        data = json.load(f)
    projects = data["projects"]

    results = []
    for proj in projects:
        try:
            result = await run_autopr(proj, dry_run=dry_run)
            results.append(result)
        except Exception as exc:
            log.error("autopr failed for %s: %s", proj["id"], exc, exc_info=True)
            results.append({"project_id": proj["id"], "pr_url": None, "fixes_applied": [], "skipped": False, "error": str(exc)})
    return results


# ─── CLI ──────────────────────────────────────────────────────────────────────


async def _main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pi-SEO auto-PR generator")
    parser.add_argument("--project", help="Single project ID (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without creating PRs")
    args = parser.parse_args()

    if args.project:
        projects_file = _HARNESS / "projects.json"
        with open(projects_file) as f:
            all_projects = json.load(f)["projects"]
        proj = next((p for p in all_projects if p["id"] == args.project), None)
        if not proj:
            log.error("Project '%s' not found", args.project)
            raise SystemExit(1)
        result = await run_autopr(proj, dry_run=args.dry_run)
        log.info("%s", json.dumps(result, indent=2))
    else:
        results = await run_autopr_all(dry_run=args.dry_run)
        log.info("%s", json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
