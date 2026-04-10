"""
scanner.py — Pi-SEO Multi-Project Scanner

Clones/updates all repos from .harness/projects.json, runs 4 scan types,
saves results to .harness/scan-results/{project-id}/{date}.json.

Scan types:
  - security:    OWASP Top 10 patterns + secret detection
  - code_quality: ruff (Python), tsc (TypeScript)
  - dependencies: npm audit, pip-audit
  - deployment_health: HTTP health checks

Usage:
    python -m app.server.scanner [--project pi-dev-ops] [--scan-type security]
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.scanner")

# ─── paths ────────────────────────────────────────────────────────────────────

_HARNESS = Path(__file__).parent.parent.parent / ".harness"
_PROJECTS_FILE = _HARNESS / "projects.json"
_RESULTS_ROOT = _HARNESS / "scan-results"
_SCAN_WORKSPACE = Path(
    os.environ.get("SCAN_WORKSPACE_ROOT", str(Path.home() / "pi-seo-workspace"))
)

# ─── data model ───────────────────────────────────────────────────────────────


@dataclass
class Finding:
    scan_type: str          # security | code_quality | dependencies | deployment_health
    severity: str           # critical | high | medium | low | info
    title: str
    description: str
    file_path: str = ""
    line_number: int = 0
    auto_fixable: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        raw = f"{self.scan_type}:{self.file_path}:{self.title}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ScanResult:
    project_id: str
    repo: str
    scan_type: str
    started_at: str
    finished_at: str
    findings: list[Finding]
    error: str = ""

    @property
    def health_score(self) -> int:
        score = 100
        for f in self.findings:
            match f.severity:
                case "critical":
                    score -= 25
                case "high":
                    score -= 10
                case "medium":
                    score -= 3
                case "low":
                    score -= 1
        return max(0, score)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["health_score"] = self.health_score
        return d


# ─── secret / dangerous patterns ──────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    (r"sk-ant-api[0-9A-Za-z\-_]{30,}", "Anthropic API key", "critical"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub personal access token", "critical"),
    (r"lin_api_[0-9A-Za-z]{40}", "Linear API key", "critical"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID", "critical"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key", "critical"),
    (r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}['\"]", "Hardcoded password", "high"),
    (r"(?i)(secret|api_key|apikey|token)\s*=\s*['\"][^'\"]{8,}['\"]", "Hardcoded secret", "high"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "Private key in source", "critical"),
    (r"(?i)bearer\s+[0-9a-zA-Z\-._~+/]{20,}", "Bearer token in source", "high"),
    (r"(?i)(?:db|database)_?(?:url|uri|connection)\s*=\s*['\"]postgresql://[^'\"]+['\"]", "DB connection string", "high"),
]

_DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"subprocess\.(?:run|Popen|call|check_output)\([^)]*shell\s*=\s*True", "shell=True subprocess", "high"),
    (r"\beval\s*\(", "eval() usage", "medium"),
    (r"dangerouslySetInnerHTML", "dangerouslySetInnerHTML", "high"),
    (r"innerHTML\s*=\s*[^'\";]+(?:req|params|query|body|input)", "innerHTML XSS risk", "high"),
    (r"(?<!log\.)(?<!//\s*)console\.log\(", "console.log in production", "low"),
    (r"(?<!\w)print\s*\((?!.*#\s*noqa)", "print() in production (Python)", "low"),
    (r"#\s*nosec\b", "security check suppressed (# nosec)", "medium"),
    (r"(?i)TODO.*(?:auth|password|secret|token|key)", "TODO near sensitive keyword", "medium"),
    (r"0\.0\.0\.0", "Binding to 0.0.0.0", "medium"),
    (r"(?i)debug\s*=\s*True", "Debug mode enabled", "high"),
]

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".next", "dist", "build",
    ".venv", "venv", "env", ".tox", "coverage", ".coverage",
}
_SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz", ".lock",
}
_TEXT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".env", ".env.example", ".md", ".sh", ".toml", ".cfg", ".ini",
    ".html", ".css", ".scss",
}


# ─── security scanner ─────────────────────────────────────────────────────────


class SecurityScanner:
    """Regex-based OWASP + secret detection over all text files."""

    def scan(self, repo_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        for file_path in self._iter_files(repo_path):
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(file_path.relative_to(repo_path))
            findings.extend(self._check_secrets(text, rel))
            findings.extend(self._check_dangerous(text, rel))
        return findings

    def _iter_files(self, root: Path):
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in _SKIP_EXTS:
                continue
            if path.suffix.lower() not in _TEXT_EXTS and path.suffix != "":
                continue
            yield path

    def _check_secrets(self, text: str, rel: str) -> list[Finding]:
        findings = []
        for pattern, title, severity in _SECRET_PATTERNS:
            for match in re.finditer(pattern, text):
                line_num = text[: match.start()].count("\n") + 1
                findings.append(
                    Finding(
                        scan_type="security",
                        severity=severity,
                        title=f"Secret detected: {title}",
                        description=f"Pattern '{pattern[:40]}' matched in {rel}:{line_num}. Rotate the credential immediately.",
                        file_path=rel,
                        line_number=line_num,
                        auto_fixable=False,
                    )
                )
        return findings

    def _check_dangerous(self, text: str, rel: str) -> list[Finding]:
        findings = []
        for pattern, title, severity in _DANGEROUS_PATTERNS:
            for match in re.finditer(pattern, text):
                line_num = text[: match.start()].count("\n") + 1
                findings.append(
                    Finding(
                        scan_type="security",
                        severity=severity,
                        title=f"Dangerous pattern: {title}",
                        description=f"Found in {rel}:{line_num}. Review and remediate.",
                        file_path=rel,
                        line_number=line_num,
                        auto_fixable=False,
                    )
                )
        return findings


# ─── dependency scanner ───────────────────────────────────────────────────────


class DependencyScanner:
    """Runs npm audit and pip-audit; maps advisories to Finding severity."""

    _SEVERITY_MAP = {
        "critical": "critical",
        "high": "high",
        "moderate": "medium",
        "medium": "medium",
        "low": "low",
        "info": "info",
    }

    async def scan(self, repo_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        tasks = []
        if (repo_path / "package.json").exists():
            tasks.append(self._npm_audit(repo_path))
        if (repo_path / "requirements.txt").exists() or (repo_path / "pyproject.toml").exists():
            tasks.append(self._pip_audit(repo_path))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    findings.extend(r)
                elif isinstance(r, Exception):
                    log.warning("Dependency scan error: %s", r)
        return findings

    async def _npm_audit(self, repo_path: Path) -> list[Finding]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "npm", "audit", "--json",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            data = json.loads(stdout)
        except (asyncio.TimeoutError, json.JSONDecodeError, FileNotFoundError) as exc:
            log.warning("npm audit failed for %s: %s", repo_path, exc)
            return []

        findings = []
        vulns = data.get("vulnerabilities", {})
        for name, vuln in vulns.items():
            severity = self._SEVERITY_MAP.get(vuln.get("severity", "low"), "low")
            via = vuln.get("via", [])
            detail = via[0] if via and isinstance(via[0], str) else (via[0].get("title", "") if via and isinstance(via[0], dict) else "")
            findings.append(
                Finding(
                    scan_type="dependencies",
                    severity=severity,
                    title=f"npm vulnerability: {name}",
                    description=f"{detail or 'No detail'}. Run `npm audit fix` to remediate.",
                    file_path="package.json",
                    auto_fixable=vuln.get("fixAvailable", False) is True,
                    extra={"package": name, "range": vuln.get("range", "")},
                )
            )
        return findings

    async def _pip_audit(self, repo_path: Path) -> list[Finding]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pip-audit", "--format=json", "--progress-spinner=off",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            data = json.loads(stdout)
        except (asyncio.TimeoutError, json.JSONDecodeError, FileNotFoundError):
            return []

        findings = []
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []):
                findings.append(
                    Finding(
                        scan_type="dependencies",
                        severity="high",
                        title=f"pip vulnerability: {dep['name']} ({vuln['id']})",
                        description=f"{vuln.get('description', 'No description')}. Fix: {vuln.get('fix_versions', [])}",
                        file_path="requirements.txt",
                        auto_fixable=bool(vuln.get("fix_versions")),
                        extra={"package": dep["name"], "vuln_id": vuln["id"]},
                    )
                )
        return findings


# ─── code quality scanner ─────────────────────────────────────────────────────


class CodeQualityScanner:
    """Runs ruff (Python) and tsc --noEmit (TypeScript)."""

    async def scan(self, repo_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        tasks = []
        py_files = list(repo_path.rglob("*.py"))
        py_files = [f for f in py_files if not any(p in _SKIP_DIRS for p in f.parts)]
        if py_files:
            tasks.append(self._ruff(repo_path))
        ts_files = list(repo_path.rglob("tsconfig.json"))
        ts_files = [f for f in ts_files if not any(p in _SKIP_DIRS for p in f.parts)]
        if ts_files:
            tasks.append(self._tsc(repo_path, ts_files[0].parent))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                findings.extend(r)
        return findings

    async def _ruff(self, repo_path: Path) -> list[Finding]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ruff", "check", ".", "--output-format=json",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            data = json.loads(stdout or "[]")
        except (asyncio.TimeoutError, json.JSONDecodeError, FileNotFoundError):
            return []

        findings = []
        for item in data[:50]:  # cap at 50 per repo
            code = item.get("code", "")
            severity = "high" if code.startswith("S") else "low"
            findings.append(
                Finding(
                    scan_type="code_quality",
                    severity=severity,
                    title=f"ruff: {code} — {item.get('message', '')}",
                    description=item.get("message", ""),
                    file_path=item.get("filename", ""),
                    line_number=item.get("location", {}).get("row", 0),
                    auto_fixable=item.get("fix") is not None,
                )
            )
        return findings

    async def _tsc(self, repo_path: Path, ts_root: Path) -> list[Finding]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "tsc", "--noEmit",
                cwd=str(ts_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = (stdout + stderr).decode("utf-8", errors="replace")
        except (asyncio.TimeoutError, FileNotFoundError):
            return []

        findings = []
        error_re = re.compile(r"^(.+?)\((\d+),\d+\): error (TS\d+): (.+)$", re.MULTILINE)
        for match in list(error_re.finditer(output))[:30]:
            rel = match.group(1).replace(str(repo_path) + "/", "")
            findings.append(
                Finding(
                    scan_type="code_quality",
                    severity="medium",
                    title=f"TypeScript error: {match.group(3)}",
                    description=match.group(4),
                    file_path=rel,
                    line_number=int(match.group(2)),
                    auto_fixable=False,
                )
            )
        return findings


# ─── deployment health scanner ────────────────────────────────────────────────


class DeploymentHealthScanner:
    """HTTP health checks for all configured deployment URLs."""

    async def scan(self, project: dict[str, Any]) -> list[Finding]:
        deployments = project.get("deployments", {})
        if not deployments:
            return []
        tasks = [
            self._check_url(name, url)
            for name, url in deployments.items()
            if url
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        findings = []
        for r in results:
            if isinstance(r, Finding):
                findings.append(r)
        return findings

    async def _check_url(self, name: str, url: str) -> Finding | None:
        import urllib.request
        import urllib.error

        try:
            loop = asyncio.get_event_loop()
            status, elapsed = await loop.run_in_executor(None, self._http_get, url)
        except Exception as exc:
            return Finding(
                scan_type="deployment_health",
                severity="critical",
                title=f"Deployment unreachable: {name}",
                description=f"{url} failed: {exc}",
                auto_fixable=False,
                extra={"url": url, "deployment": name},
            )

        if status >= 500:
            return Finding(
                scan_type="deployment_health",
                severity="critical",
                title=f"Deployment 5xx: {name}",
                description=f"{url} returned HTTP {status}.",
                auto_fixable=False,
                extra={"url": url, "status": status, "deployment": name},
            )
        if status >= 400:
            return Finding(
                scan_type="deployment_health",
                severity="high",
                title=f"Deployment 4xx: {name}",
                description=f"{url} returned HTTP {status}.",
                auto_fixable=False,
                extra={"url": url, "status": status, "deployment": name},
            )
        if elapsed > 3.0:
            return Finding(
                scan_type="deployment_health",
                severity="medium",
                title=f"Deployment slow response: {name}",
                description=f"{url} responded in {elapsed:.1f}s (threshold: 3s).",
                auto_fixable=False,
                extra={"url": url, "latency_s": elapsed, "deployment": name},
            )
        return None

    @staticmethod
    def _http_get(url: str) -> tuple[int, float]:
        import urllib.request
        start = time.monotonic()
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Pi-SEO-Scanner/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read(1024)
        return resp.status, time.monotonic() - start


# ─── project scanner (orchestrator) ───────────────────────────────────────────


class ProjectScanner:
    """Orchestrates all scan types across all projects in projects.json."""

    def __init__(self) -> None:
        self._security = SecurityScanner()
        self._deps = DependencyScanner()
        self._quality = CodeQualityScanner()
        self._health = DeploymentHealthScanner()
        self._semaphore = asyncio.Semaphore(3)

    def load_projects(self) -> list[dict[str, Any]]:
        with open(_PROJECTS_FILE) as f:
            data = json.load(f)
        return data["projects"]

    async def scan_project(
        self,
        project: dict[str, Any],
        scan_types: list[str] | None = None,
    ) -> list[ScanResult]:
        """Scan a single project. Returns one ScanResult per scan type."""
        async with self._semaphore:
            pid = project["id"]
            repo = project["repo"]
            types = scan_types or ["security", "code_quality", "dependencies", "deployment_health"]
            results = []

            repo_path = await self._clone_or_update(repo)

            for scan_type in types:
                started = datetime.now(timezone.utc).isoformat()
                findings: list[Finding] = []
                error = ""
                try:
                    match scan_type:
                        case "security":
                            findings = self._security.scan(repo_path)
                        case "code_quality":
                            findings = await self._quality.scan(repo_path)
                        case "dependencies":
                            findings = await self._deps.scan(repo_path)
                        case "deployment_health":
                            findings = await self._health.scan(project)
                except Exception as exc:
                    error = str(exc)
                    log.error("Scan %s/%s failed: %s", pid, scan_type, exc, exc_info=True)

                result = ScanResult(
                    project_id=pid,
                    repo=repo,
                    scan_type=scan_type,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    findings=findings,
                    error=error,
                )
                self._save_result(result)
                results.append(result)
                log.info(
                    "Scanned %s/%s: %d findings, health=%d",
                    pid, scan_type, len(findings), result.health_score,
                )

            return results

    async def scan_all(
        self,
        priority: str | None = None,
        scan_types: list[str] | None = None,
    ) -> dict[str, list[ScanResult]]:
        """Scan all projects (optionally filtered by scan_priority)."""
        projects = self.load_projects()
        if priority:
            projects = [p for p in projects if p.get("scan_priority") == priority]

        tasks = [self.scan_project(p, scan_types) for p in projects]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, list[ScanResult]] = {}
        for proj, result in zip(projects, all_results):
            if isinstance(result, list):
                out[proj["id"]] = result
            else:
                log.error("Project scan failed %s: %s", proj["id"], result)
                out[proj["id"]] = []
        return out

    async def _clone_or_update(self, repo: str) -> Path:
        """Clone repo if missing, git pull if older than 1 hour."""
        _SCAN_WORKSPACE.mkdir(parents=True, exist_ok=True)
        repo_name = repo.split("/")[-1]
        repo_path = _SCAN_WORKSPACE / repo_name

        if not repo_path.exists():
            log.info("Cloning %s", repo)
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth=1",
                f"git@github.com:{repo}.git",
                str(repo_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                raise RuntimeError(f"git clone failed: {stderr.decode()[:200]}")
            return repo_path

        # check staleness via .git/FETCH_HEAD mtime
        fetch_head = repo_path / ".git" / "FETCH_HEAD"
        stale = True
        if fetch_head.exists():
            stale = (time.time() - fetch_head.stat().st_mtime) > 3600

        if stale:
            log.info("Pulling %s", repo)
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "--ff-only",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)

        return repo_path

    def _save_result(self, result: ScanResult) -> None:
        out_dir = _RESULTS_ROOT / result.project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_file = out_dir / f"{date_str}-{result.scan_type}.json"
        with open(out_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    def get_health_summary(self) -> list[dict[str, Any]]:
        """Read the latest scan results for each project and return health scores."""
        projects = self.load_projects()
        summary = []
        for proj in projects:
            pid = proj["id"]
            result_dir = _RESULTS_ROOT / pid
            scores: dict[str, int] = {}
            findings_count: dict[str, int] = {}
            if result_dir.exists():
                for scan_type in ["security", "code_quality", "dependencies", "deployment_health"]:
                    files = sorted(result_dir.glob(f"*-{scan_type}.json"))
                    if files:
                        try:
                            data = json.loads(files[-1].read_text())
                            scores[scan_type] = data.get("health_score", 100)
                            findings_count[scan_type] = len(data.get("findings", []))
                        except (json.JSONDecodeError, OSError):
                            pass
            overall = int(sum(scores.values()) / len(scores)) if scores else 100
            summary.append({
                "project_id": pid,
                "repo": proj["repo"],
                "overall_health": overall,
                "scores": scores,
                "findings_count": findings_count,
                "deployments": proj.get("deployments", {}),
            })
        return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────


async def _main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Pi-SEO multi-project scanner")
    parser.add_argument("--project", help="Scan a single project ID (default: all)")
    parser.add_argument(
        "--scan-type",
        choices=["security", "code_quality", "dependencies", "deployment_health"],
        help="Limit to one scan type",
    )
    parser.add_argument("--priority", choices=["high", "medium", "low"], help="Filter by scan_priority")
    parser.add_argument("--summary", action="store_true", help="Print health summary only")
    args = parser.parse_args()

    scanner = ProjectScanner()

    if args.summary:
        print(json.dumps(scanner.get_health_summary(), indent=2))
        return

    scan_types = [args.scan_type] if args.scan_type else None

    if args.project:
        projects = scanner.load_projects()
        proj = next((p for p in projects if p["id"] == args.project), None)
        if not proj:
            print(f"Project '{args.project}' not found in projects.json")
            raise SystemExit(1)
        results = await scanner.scan_project(proj, scan_types)
        for r in results:
            print(json.dumps({k: v for k, v in r.to_dict().items() if k != "findings"}, indent=2))
    else:
        all_results = await scanner.scan_all(priority=args.priority, scan_types=scan_types)
        for pid, results in all_results.items():
            for r in results:
                print(json.dumps({k: v for k, v in r.to_dict().items() if k != "findings"}, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
