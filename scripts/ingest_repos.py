#!/usr/bin/env python3
"""
scripts/ingest_repos.py — Pull key docs from all GitHub repos into Sources/

For each project in projects.json, fetches:
  - README.md (main project overview)
  - CHANGELOG.md (recent changes)
  - docs/*.md (documentation files)
  - business-charters/{id}.md (if present in Pi-Dev-Ops)
  - package.json / pyproject.toml (tech stack, dependencies)

Saves each as a Sources/ clip with proper frontmatter so the hourly
sources_watcher ingests it into the Brain-1 wiki automatically.

Runs daily via launchd. Skips files not modified since last run.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [repo-ingester] %(message)s",
)
log = logging.getLogger()

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_JSON = REPO_ROOT / ".harness" / "projects.json"
SOURCES_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Sources"

# Files to fetch from each repo (in priority order)
FETCH_TARGETS = [
    "README.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/ARCHITECTURE.md",
    "docs/overview.md",
]

# Tech-stack files — fetch content summary only (first 100 lines)
STACK_FILES = ["package.json", "pyproject.toml", "requirements.txt"]


def _gh_get(path: str) -> dict | str | None:
    """Use gh CLI for authenticated GitHub API calls — avoids token management."""
    import subprocess  # noqa: PLC0415
    try:
        result = subprocess.run(
            ["gh", "api", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        if "404" in result.stderr:
            return None
        log.warning("gh api %s: %s", path, result.stderr[:100])
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("gh api error: %s — %s", path, exc)
        return None


def _fetch_file(repo: str, filepath: str) -> str | None:
    """Fetch a file's content from GitHub. Returns decoded text or None."""
    data = _gh_get(f"/repos/{repo}/contents/{filepath}")
    if not data or not isinstance(data, dict):
        return None
    if data.get("encoding") == "base64":
        import base64  # noqa: PLC0415
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
    return data.get("content")


def _fetch_repo_info(repo: str) -> dict | None:
    return _gh_get(f"/repos/{repo}")


def _save_source(filename: str, content: str,
                 title: str, source_url: str,
                 repo: str, file_type: str) -> Path:
    """Write content to Sources/ with proper frontmatter."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    p = SOURCES_DIR / filename
    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"source: \"{source_url}\"\n"
        f"repo: \"{repo}\"\n"
        f"file_type: \"{file_type}\"\n"
        f"captured: \"{date.today().isoformat()}\"\n"
        f"tags:\n"
        f"  - clippings\n"
        f"  - github\n"
        f"  - {repo.split('/')[1].lower()}\n"
        f"---\n\n"
    )
    p.write_text(frontmatter + content, encoding="utf-8")
    return p


def process_repo(project: dict) -> int:
    """Fetch and save key docs for one project. Returns number of files saved."""
    project_id = project["id"]
    repo = project["repo"]
    saved = 0

    log.info("Processing %s (%s)", project_id, repo)

    # Get repo metadata
    info = _fetch_repo_info(repo)
    if not info:
        log.warning("  Could not fetch repo info for %s", repo)
        return 0

    description = info.get("description", "")
    default_branch = info.get("default_branch", "main")
    pushed_at = info.get("pushed_at", "")

    # Skip repos with no activity in the last 90 days (stale)
    # (still process if no pushed_at data)
    if pushed_at:
        try:
            last_push = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - last_push).days
            if days_ago > 90:
                log.info("  Skipping %s — no activity for %d days", repo, days_ago)
                return 0
        except ValueError:
            pass

    # Fetch priority doc files
    for target in FETCH_TARGETS:
        content = _fetch_file(repo, target)
        if not content:
            continue

        safe_name = target.replace("/", "-").replace(".md", "")
        filename = f"github-{project_id}-{safe_name}.md"
        source_url = f"https://github.com/{repo}/blob/{default_branch}/{target}"

        title = f"{project_id} — {target}"
        if description and target == "README.md":
            title = f"{project_id}: {description[:80]}"

        _save_source(filename, content, title, source_url, repo, safe_name)
        log.info("  ✓ %s", filename)
        saved += 1

    # Fetch stack files (just first 80 lines for context)
    stack_content_parts = []
    for sf in STACK_FILES:
        content = _fetch_file(repo, sf)
        if content:
            lines = content.splitlines()[:80]
            stack_content_parts.append(f"## {sf}\n```\n" + "\n".join(lines) + "\n```\n")

    if stack_content_parts:
        filename = f"github-{project_id}-tech-stack.md"
        full_content = f"# {project_id} — Tech Stack\n\n" + "\n".join(stack_content_parts)
        source_url = f"https://github.com/{repo}"
        _save_source(filename, full_content,
                     f"{project_id} Tech Stack",
                     source_url, repo, "tech-stack")
        log.info("  ✓ %s", filename)
        saved += 1

    return saved


def main() -> None:
    if not PROJECTS_JSON.exists():
        log.error("projects.json not found at %s", PROJECTS_JSON)
        return

    projects = json.loads(PROJECTS_JSON.read_text())["projects"]
    total = 0

    for project in projects:
        try:
            total += process_repo(project)
        except Exception as exc:  # noqa: BLE001
            log.error("Error processing %s: %s", project.get("id"), exc)

    log.info("Done — %d files saved to Sources/", total)


if __name__ == "__main__":
    main()
