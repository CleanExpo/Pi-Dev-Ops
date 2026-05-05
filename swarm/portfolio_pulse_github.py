"""swarm/portfolio_pulse_github.py — RA-1889 (child of RA-1409).

GitHub-data section provider for the daily Portfolio Pulse. Plugs into
the foundation (RA-1888) via ``portfolio_pulse.set_section_provider``.

For each project, queries the GitHub REST API for the last 24h of:
  * Recent main-branch commits (proxy for deploys; deploy-status best
    effort, ``unknown`` when Vercel/Railway APIs aren't wired)
  * CI workflow run pass/fail counts on main + top 3 failures
  * Open PRs — total count, oldest, and stale (no update >3 days)

The provider is registered at module import time, so any caller that
imports this module gets the upgraded sections (``deploys``, ``ci``,
``prs``). Foundation's placeholders are replaced.

Constraints from RA-1889:
  * stdlib only — urllib.request + json, no httpx/requests
  * All HTTP errors swallowed and logged — pulse must not break on
    GitHub outage
  * GITHUB_TOKEN absent → synthetic placeholder body
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import portfolio_pulse

log = logging.getLogger("swarm.portfolio_pulse.github")

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_JSON_REL = ".harness/projects.json"

GH_API_BASE = "https://api.github.com"
HTTP_TIMEOUT_S = 8.0

DEFAULT_LOOKBACK_HOURS = 24
STALE_PR_DAYS = 3
TOP_FAILURES_COUNT = 3
TOP_STALE_PR_COUNT = 3
PER_PAGE = 50


# ── Project lookup ──────────────────────────────────────────────────────────


def _load_projects(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Load .harness/projects.json keyed by project id."""
    p = repo_root / PROJECTS_JSON_REL
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_github: projects.json parse failed: %s", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for proj in data.get("projects", []) or []:
        pid = proj.get("id")
        if pid:
            out[pid] = proj
    return out


# ── HTTP ────────────────────────────────────────────────────────────────────


def _gh_get(path: str, *, params: dict[str, Any] | None = None,
              token: str = "") -> Any:
    """One GitHub API GET via stdlib. Raises HTTPError/URLError on failure.

    Caller is responsible for swallowing errors at the section boundary.
    """
    url = f"{GH_API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pi-ceo-portfolio-pulse",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Data fetchers ───────────────────────────────────────────────────────────


def recent_deploys(repo: str, since_iso: str,
                     *, token: str = "") -> list[dict]:
    """Main-branch commits in the last 24h, with best-effort deploy status.

    Vercel/Railway APIs aren't wired in this ticket — every commit is
    returned with ``deploy_status="unknown"``. A follow-up ticket can
    layer real status by calling the deploy provider per commit_sha.

    Returns a list of dicts with keys: sha, message, author, committed_at,
    url, deploy_status. Empty list on error or empty repo.
    """
    try:
        commits = _gh_get(
            f"/repos/{repo}/commits",
            params={"sha": "main", "since": since_iso, "per_page": PER_PAGE},
            token=token,
        )
    except (HTTPError, URLError, ValueError, OSError) as exc:
        log.warning("portfolio_pulse_github: deploys fetch failed for %s (%s)",
                    repo, exc)
        return []

    out: list[dict] = []
    for c in commits or []:
        commit = c.get("commit") or {}
        author = (commit.get("author") or {}).get("name", "unknown")
        out.append({
            "sha": (c.get("sha") or "")[:7],
            "message": (commit.get("message") or "").splitlines()[0][:80],
            "author": author,
            "committed_at": (commit.get("author") or {}).get("date", ""),
            "url": c.get("html_url", ""),
            "deploy_status": "unknown",
        })
    return out


def ci_summary(repo: str, since_iso: str,
                 *, token: str = "") -> dict:
    """Workflow runs on main in the last 24h.

    Returns ``{pass_count, fail_count, recent_failures: [...]}``. Failures
    list is capped at ``TOP_FAILURES_COUNT``. Empty/zero on error.
    """
    empty = {"pass_count": 0, "fail_count": 0, "recent_failures": []}
    try:
        data = _gh_get(
            f"/repos/{repo}/actions/runs",
            params={
                "branch": "main",
                "created": f">={since_iso[:10]}",
                "per_page": PER_PAGE,
            },
            token=token,
        )
    except (HTTPError, URLError, ValueError, OSError) as exc:
        log.warning("portfolio_pulse_github: ci fetch failed for %s (%s)",
                    repo, exc)
        return empty

    runs = (data or {}).get("workflow_runs") or []
    # Filter to runs created within the lookback window (since GitHub's
    # `created` query is day-precision; we want hour-precision).
    cutoff = _parse_iso(since_iso)
    pass_count = 0
    fail_count = 0
    failures: list[dict] = []
    for r in runs:
        if r.get("status") != "completed":
            continue
        created = _parse_iso(r.get("created_at") or "")
        if cutoff and created and created < cutoff:
            continue
        conclusion = r.get("conclusion")
        if conclusion == "success":
            pass_count += 1
        elif conclusion == "failure":
            fail_count += 1
            if len(failures) < TOP_FAILURES_COUNT:
                failures.append({
                    "name": r.get("name", ""),
                    "url": r.get("html_url", ""),
                    "commit_sha": (r.get("head_sha") or "")[:7],
                })
    return {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "recent_failures": failures,
    }


def pr_summary(repo: str, *, token: str = "") -> dict:
    """Open PR count, oldest open PR, and stale (>3d no update) PRs.

    Returns ``{open_count, oldest_pr, stale_prs: [...]}``. ``oldest_pr``
    is None when there are no open PRs. Empty/zero on error.
    """
    empty: dict[str, Any] = {"open_count": 0, "oldest_pr": None, "stale_prs": []}
    try:
        prs = _gh_get(
            f"/repos/{repo}/pulls",
            params={
                "state": "open", "sort": "created", "direction": "asc",
                "per_page": PER_PAGE,
            },
            token=token,
        )
    except (HTTPError, URLError, ValueError, OSError) as exc:
        log.warning("portfolio_pulse_github: prs fetch failed for %s (%s)",
                    repo, exc)
        return empty

    if not prs:
        return empty

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_PR_DAYS)

    formatted = [{
        "number": p.get("number"),
        "title": (p.get("title") or "")[:80],
        "url": p.get("html_url", ""),
        "user": (p.get("user") or {}).get("login", "unknown"),
        "created_at": p.get("created_at", ""),
        "updated_at": p.get("updated_at", ""),
    } for p in prs]

    oldest = formatted[0] if formatted else None

    stale: list[dict] = []
    for fp in formatted:
        ua = _parse_iso(fp.get("updated_at") or "")
        if ua and ua < stale_cutoff:
            stale.append(fp)
        if len(stale) >= TOP_STALE_PR_COUNT:
            break

    return {
        "open_count": len(formatted),
        "oldest_pr": oldest,
        "stale_prs": stale,
    }


# ── Markdown rendering ──────────────────────────────────────────────────────


def _window_label(lookback_hours: int) -> str:
    """Render a human-readable window label for section bodies — e.g.
    'last 24h' for the daily pulse, 'last 7 days' for the Friday recap."""
    if lookback_hours >= 168:
        days = lookback_hours // 24
        return f"last {days} days"
    return f"last {lookback_hours}h"


def _render_deploys(deploys: list[dict],
                     *, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> str:
    label = _window_label(lookback_hours)
    if not deploys:
        return f"_(no main-branch commits in the {label})_"
    # Show up to 5 by default, but for weekly windows show more so the
    # operator gets the actual list of wins this week.
    cap = 5 if lookback_hours <= 24 else 12
    lines = [f"- **Commits to main ({label}):** {len(deploys)}"]
    for d in deploys[:cap]:
        lines.append(
            f"    - `{d['sha']}` by {d['author']} "
            f"[{d['deploy_status']}] — {d['message']}"
        )
    if len(deploys) > cap:
        lines.append(f"    - …and {len(deploys) - cap} more")
    return "\n".join(lines)


def _render_ci(summary: dict,
                *, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> str:
    p = summary.get("pass_count", 0)
    f = summary.get("fail_count", 0)
    failures = summary.get("recent_failures", []) or []
    label = _window_label(lookback_hours)
    lines = [f"- **Workflow runs (main, {label}):** {p} passed · {f} failed"]
    if failures:
        lines.append("- **Recent failures:**")
        for fail in failures:
            lines.append(
                f"    - {fail.get('name', '?')} "
                f"@ `{fail.get('commit_sha', '')}` — {fail.get('url', '')}"
            )
    return "\n".join(lines)


def _render_prs(summary: dict) -> str:
    open_count = summary.get("open_count", 0)
    oldest = summary.get("oldest_pr")
    stale = summary.get("stale_prs", []) or []
    lines = [f"- **Open PRs:** {open_count}"]
    if oldest:
        lines.append(
            f"    - Oldest: #{oldest.get('number')} "
            f"({(oldest.get('created_at') or '')[:10]}) "
            f"— {oldest.get('title', '')}"
        )
    lines.append(f"- **Stale (no update >{STALE_PR_DAYS}d):** {len(stale)}")
    for pr in stale:
        lines.append(
            f"    - #{pr.get('number')} by {pr.get('user')} "
            f"— last updated {(pr.get('updated_at') or '')[:10]} "
            f"— {pr.get('title', '')}"
        )
    return "\n".join(lines)


# ── Provider ────────────────────────────────────────────────────────────────


def _resolve_repo(project_id: str, repo_root: Path) -> str | None:
    """Lookup the GitHub repo (owner/name) for a project from projects.json."""
    projects = _load_projects(repo_root)
    proj = projects.get(project_id) or {}
    repo = proj.get("repo") or ""
    return repo or None


def _no_token_section(section: str) -> tuple[str, str | None]:
    return f"_(GitHub token not configured — {section} unavailable)_", "no_token"


def _no_repo_section(project_id: str) -> tuple[str, str | None]:
    return (
        f"_(github: project_id {project_id!r} has no `repo` mapping in "
        ".harness/projects.json)_",
        "no_repo_mapping",
    )


def deploys_provider(project_id: str,
                       repo_root: Path) -> tuple[str, str | None]:
    """Section provider for the ``deploys`` slot.

    Honours the active ``portfolio_pulse.get_lookback_hours()`` so the
    weekly Friday recap (RA-2006) widens the window to 168h via the same
    machinery as the daily 24h pulse.
    """
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return _no_token_section("deploys")
    repo = _resolve_repo(project_id, repo_root)
    if not repo:
        return _no_repo_section(project_id)
    lookback_h = portfolio_pulse.get_lookback_hours()
    since = (datetime.now(timezone.utc)
             - timedelta(hours=lookback_h)).isoformat()
    deploys = recent_deploys(repo, since, token=token)
    return _render_deploys(deploys, lookback_hours=lookback_h), None


def ci_provider(project_id: str,
                  repo_root: Path) -> tuple[str, str | None]:
    """Section provider for the ``ci`` slot. Honours active lookback (RA-2006)."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return _no_token_section("ci")
    repo = _resolve_repo(project_id, repo_root)
    if not repo:
        return _no_repo_section(project_id)
    lookback_h = portfolio_pulse.get_lookback_hours()
    since = (datetime.now(timezone.utc)
             - timedelta(hours=lookback_h)).isoformat()
    summary = ci_summary(repo, since, token=token)
    return _render_ci(summary, lookback_hours=lookback_h), None


def prs_provider(project_id: str,
                   repo_root: Path) -> tuple[str, str | None]:
    """Section provider for the ``prs`` slot."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return _no_token_section("prs")
    repo = _resolve_repo(project_id, repo_root)
    if not repo:
        return _no_repo_section(project_id)
    summary = pr_summary(repo, token=token)
    return _render_prs(summary), None


# Composite "github" provider exposed in the task contract — combines
# all three sections into one body. Useful for callers that want a
# single rendered block rather than the three-slot dispatch.
def provider(project_id: str,
               repo_root: Path) -> portfolio_pulse.PulseSection:
    """Composite GitHub PulseSection — combined deploys + ci + prs body."""
    deploy_body, deploy_err = deploys_provider(project_id, repo_root)
    ci_body, ci_err = ci_provider(project_id, repo_root)
    pr_body, pr_err = prs_provider(project_id, repo_root)
    body = (
        f"### Deploys\n{deploy_body}\n\n"
        f"### CI\n{ci_body}\n\n"
        f"### PRs\n{pr_body}"
    )
    err = deploy_err or ci_err or pr_err
    return portfolio_pulse.PulseSection(name="github", body_md=body,
                                          error=err)


def register() -> None:
    """Idempotent registration. Replaces foundation placeholders for the
    three GitHub-backed sections."""
    portfolio_pulse.set_section_provider("deploys", deploys_provider)
    portfolio_pulse.set_section_provider("ci", ci_provider)
    portfolio_pulse.set_section_provider("prs", prs_provider)


# Self-register on import — sibling-child plug-point convention.
register()


__all__ = [
    "recent_deploys", "ci_summary", "pr_summary",
    "deploys_provider", "ci_provider", "prs_provider",
    "provider", "register",
    "DEFAULT_LOOKBACK_HOURS", "STALE_PR_DAYS",
    "TOP_FAILURES_COUNT", "TOP_STALE_PR_COUNT",
]
