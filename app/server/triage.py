"""
triage.py — Pi-SEO Finding Triage Engine

Deduplicates findings by SHA256 fingerprint against a local cache and
the Linear board, then creates tickets in the correct Linear project/team.

Routes findings via .harness/projects.json:
  - Uses linear_project_id (or linear_team_id if no project) per repo
  - Ticket format: [Pi-SEO][scan_type] Title

Usage:
    from app.server.triage import TriageEngine
    engine = TriageEngine()
    created = engine.triage(project_id, scan_results)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.server.scanner import Finding, ScanResult

log = logging.getLogger("pi-ceo.triage")

# ─── paths ────────────────────────────────────────────────────────────────────

_HARNESS = Path(__file__).parent.parent.parent / ".harness"
_PROJECTS_FILE = _HARNESS / "projects.json"
_CACHE_FILE = _HARNESS / "triage-cache.json"

# Skip low-severity items to avoid noise
_MIN_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_TRIAGE_THRESHOLD = 1  # create tickets for low and above

# ─── Linear GraphQL client ────────────────────────────────────────────────────

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


class LinearClient:
    """Minimal Linear GraphQL client using only stdlib."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            _LINEAR_ENDPOINT,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Linear HTTP {exc.code}: {body}") from exc
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def create_issue(
        self,
        team_id: str,
        title: str,
        description: str,
        priority: int,
        project_id: str | None = None,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    url
                    title
                }
            }
        }
        """
        variables: dict[str, Any] = {
            "input": {
                "teamId": team_id,
                "title": title,
                "description": description,
                "priority": priority,
            }
        }
        if project_id:
            variables["input"]["projectId"] = project_id
        if label_ids:
            variables["input"]["labelIds"] = label_ids
        data = self._gql(mutation, variables)
        result = data.get("issueCreate", {})
        if not result.get("success"):
            raise RuntimeError(f"issueCreate returned success=false for title='{title}'")
        return result.get("issue", {})

    def search_issues(self, team_id: str, title_contains: str) -> list[dict[str, Any]]:
        query = """
        query SearchIssues($filter: IssueFilter!) {
            issues(filter: $filter, first: 5) {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                }
            }
        }
        """
        variables = {
            "filter": {
                "team": {"id": {"eq": team_id}},
                "title": {"containsIgnoreCase": title_contains},
            }
        }
        try:
            data = self._gql(query, variables)
            return data.get("issues", {}).get("nodes", [])
        except RuntimeError:
            return []

    def get_or_create_label(self, team_id: str, label_name: str, color: str = "#F2994A") -> str | None:
        """Return label ID if it exists, else create it."""
        query = """
        query GetLabels($teamId: String!) {
            issueLabels(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name }
            }
        }
        """
        try:
            data = self._gql(query, {"teamId": team_id})
            for label in data.get("issueLabels", {}).get("nodes", []):
                if label["name"].lower() == label_name.lower():
                    return label["id"]
        except RuntimeError:
            return None

        # Create it
        mutation = """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel { id }
            }
        }
        """
        try:
            data = self._gql(mutation, {"input": {"teamId": team_id, "name": label_name, "color": color}})
            return data.get("issueLabelCreate", {}).get("issueLabel", {}).get("id")
        except RuntimeError:
            return None


# ─── fingerprint cache ────────────────────────────────────────────────────────


class FingerprintCache:
    """Persists seen fingerprints to .harness/triage-cache.json."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if _CACHE_FILE.exists():
            try:
                self._data = json.loads(_CACHE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        _HARNESS.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(self._data, indent=2))

    def is_known(self, fingerprint: str) -> bool:
        return fingerprint in self._data

    def mark(self, fingerprint: str, linear_id: str, title: str) -> None:
        self._data[fingerprint] = {
            "linear_id": linear_id,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def prune_older_than_days(self, days: int = 90) -> None:
        cutoff = time.time() - days * 86400
        self._data = {
            fp: v for fp, v in self._data.items()
            if _parse_ts(v.get("created_at", "")) > cutoff
        }
        self._save()


def _parse_ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ─── triage engine ────────────────────────────────────────────────────────────

_SEVERITY_TO_LINEAR_PRIORITY = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 4,
}

_SCAN_TYPE_LABEL = {
    "security": "Pi-SEO: Security",
    "code_quality": "Pi-SEO: Code Quality",
    "dependencies": "Pi-SEO: Dependencies",
    "deployment_health": "Pi-SEO: Deployment",
}


class TriageEngine:
    """Routes findings to the correct Linear project/team, deduplicating via fingerprints."""

    def __init__(self) -> None:
        api_key = os.environ.get("LINEAR_API_KEY", "")
        if not api_key:
            log.warning("LINEAR_API_KEY not set — triage will run in dry-run mode")
        self._client = LinearClient(api_key) if api_key else None
        self._cache = FingerprintCache()
        self._projects = self._load_projects()
        self._label_cache: dict[str, str | None] = {}  # team_id -> label_id

    def _load_projects(self) -> dict[str, dict[str, Any]]:
        with open(_PROJECTS_FILE) as f:
            data = json.load(f)
        return {p["id"]: p for p in data["projects"]}

    def triage(
        self,
        project_id: str,
        scan_results: list[ScanResult],
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Process findings for a project. Returns list of created ticket dicts.
        Skips findings below threshold, deduplicates against cache + Linear.
        """
        project = self._projects.get(project_id)
        if not project:
            log.error("Unknown project_id: %s", project_id)
            return []

        team_id = project["linear_team_id"]
        project_linear_id = project.get("linear_project_id")
        created: list[dict[str, Any]] = []

        for result in scan_results:
            for finding in result.findings:
                if _SEVERITY_TO_LINEAR_PRIORITY.get(finding.severity, 4) > _TRIAGE_THRESHOLD + 3:
                    continue  # skip info
                if _MIN_SEVERITY_RANK.get(finding.severity, 0) < _TRIAGE_THRESHOLD:
                    continue

                fp = finding.fingerprint
                if self._cache.is_known(fp):
                    log.debug("Skipping known finding: %s", fp)
                    continue

                title = self._build_title(finding)
                description = self._build_description(finding, result)

                # Check Linear for duplicates
                if self._client and not dry_run:
                    existing = self._client.search_issues(team_id, title[:60])
                    if existing:
                        log.info("Duplicate found in Linear for '%s', caching", title[:60])
                        self._cache.mark(fp, existing[0]["id"], title)
                        continue

                priority = _SEVERITY_TO_LINEAR_PRIORITY.get(finding.severity, 4)

                if dry_run or not self._client:
                    log.info("[DRY RUN] Would create: %s (priority=%d)", title, priority)
                    self._cache.mark(fp, "dry-run", title)
                    created.append({"title": title, "priority": priority, "dry_run": True})
                    continue

                label_id = self._get_label(team_id, finding.scan_type)

                try:
                    issue = self._client.create_issue(
                        team_id=team_id,
                        title=title,
                        description=description,
                        priority=priority,
                        project_id=project_linear_id,
                        label_ids=[label_id] if label_id else None,
                    )
                    self._cache.mark(fp, issue["id"], title)
                    log.info(
                        "Created %s: %s [%s]",
                        issue.get("identifier", "?"),
                        title[:60],
                        finding.severity,
                    )
                    created.append(issue)
                except RuntimeError as exc:
                    log.error("Failed to create issue for '%s': %s", title[:60], exc)

        return created

    def triage_all(
        self,
        all_results: dict[str, list[ScanResult]],
        dry_run: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Triage findings for all projects."""
        out = {}
        for project_id, results in all_results.items():
            out[project_id] = self.triage(project_id, results, dry_run=dry_run)
        return out

    def _build_title(self, finding: Finding) -> str:
        scan_label = finding.scan_type.replace("_", " ").title()
        return f"[Pi-SEO][{scan_label}] {finding.title}"

    def _build_description(self, finding: Finding, result: ScanResult) -> str:
        lines = [
            f"**Severity:** {finding.severity.upper()}",
            f"**Project:** {result.project_id} (`{result.repo}`)",
            f"**Scan type:** {finding.scan_type}",
            f"**Detected:** {result.started_at}",
            "",
            "---",
            "",
            finding.description,
        ]
        if finding.file_path:
            lines.append(f"\n**File:** `{finding.file_path}`" +
                         (f" line {finding.line_number}" if finding.line_number else ""))
        if finding.auto_fixable:
            lines.append("\n> This finding may be auto-fixable.")
        if finding.extra:
            lines.append(f"\n**Extra:** `{json.dumps(finding.extra)}`")
        lines += [
            "",
            "---",
            f"*Generated by Pi-SEO autonomous scanner — fingerprint `{finding.fingerprint}`*",
        ]
        return "\n".join(lines)

    def _get_label(self, team_id: str, scan_type: str) -> str | None:
        if not self._client:
            return None
        label_name = _SCAN_TYPE_LABEL.get(scan_type, "Pi-SEO")
        cache_key = f"{team_id}:{label_name}"
        if cache_key not in self._label_cache:
            self._label_cache[cache_key] = self._client.get_or_create_label(team_id, label_name)
        return self._label_cache[cache_key]


# ─── CLI ──────────────────────────────────────────────────────────────────────


async def _main() -> None:
    import argparse
    import asyncio
    from app.server.scanner import ProjectScanner

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Pi-SEO triage engine")
    parser.add_argument("--project", help="Triage a single project ID")
    parser.add_argument("--dry-run", action="store_true", help="Simulate ticket creation")
    parser.add_argument("--scan-type", help="Limit scan type")
    args = parser.parse_args()

    scanner = ProjectScanner()
    engine = TriageEngine()

    scan_types = [args.scan_type] if args.scan_type else None

    if args.project:
        projects = scanner.load_projects()
        proj = next((p for p in projects if p["id"] == args.project), None)
        if not proj:
            print(f"Project '{args.project}' not found")
            raise SystemExit(1)
        results = await scanner.scan_project(proj, scan_types)
        created = engine.triage(args.project, results, dry_run=args.dry_run)
        print(json.dumps(created, indent=2))
    else:
        all_results = await scanner.scan_all(scan_types=scan_types)
        all_created = engine.triage_all(all_results, dry_run=args.dry_run)
        total = sum(len(v) for v in all_created.values())
        print(f"Total tickets created: {total}")
        print(json.dumps(all_created, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
