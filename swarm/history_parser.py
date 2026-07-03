"""swarm/history_parser.py — RA-6472 historical-conversation parser (v1).

Sweeps a GitHub repo's issues and pull requests and classifies each work
item into one of four lifecycle states, producing a per-project map of what
was implemented / started / abandoned / never built. This is the first
increment of the 2026-06-10 Plaud mandate: "map what's been implemented,
started, completed, still needed" across the portfolio, paying clients first.

Classification is pure and offline-testable; the network layer is a single
injectable ``gh_get`` (reused from portfolio_pulse_github) so callers/tests
can supply fixtures.

Public API:
    classify_issue(issue) -> Status
    classify_pr(pr)       -> Status
    parse_repo(repo, ...) -> RepoHistoryMap
    render_map(m)         -> str
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from swarm.portfolio_pulse_github import _gh_get

log = logging.getLogger("swarm.history_parser")

Status = Literal["implemented", "started", "abandoned", "never_built"]

STATUS_ORDER: tuple[Status, ...] = ("implemented", "started", "abandoned", "never_built")

# Bound API usage; each page is up to PER_PAGE items. Both are injectable.
PER_PAGE = 50
MAX_PAGES = 3


@dataclass
class WorkItem:
    kind: str  # "issue" | "pr"
    number: int
    title: str
    status: Status
    url: str
    updated_at: str


@dataclass
class RepoHistoryMap:
    repo: str
    items: list[WorkItem] = field(default_factory=list)

    def counts(self) -> dict[Status, int]:
        out: dict[Status, int] = {s: 0 for s in STATUS_ORDER}
        for it in self.items:
            out[it.status] += 1
        return out

    def by_status(self, status: Status) -> list[WorkItem]:
        return [it for it in self.items if it.status == status]


# ── Classification (pure) ────────────────────────────────────────────────────


def is_pull_request(issue: dict) -> bool:
    """The GitHub issues endpoint returns PRs too; they carry a ``pull_request`` key."""
    return "pull_request" in issue


def classify_issue(issue: dict) -> Status:
    """Lifecycle state for a GitHub issue.

    Closed issues resolve by ``state_reason`` (completed vs not_planned); a
    closed issue with no reason (older issues predate the field) is treated as
    implemented, since a closed issue is normally done work. Open issues split
    on whether anyone owns them: an assigned open issue is in flight
    (``started``); an unassigned open issue is a logged idea nobody built
    (``never_built``).
    """
    state = (issue.get("state") or "").lower()
    if state == "closed":
        reason = (issue.get("state_reason") or "").lower()
        return "abandoned" if reason == "not_planned" else "implemented"
    assignee = issue.get("assignee")
    assignees = issue.get("assignees") or []
    if assignee or assignees:
        return "started"
    return "never_built"


def classify_pr(pr: dict) -> Status:
    """Lifecycle state for a pull request: merged→implemented, open→started,
    closed-unmerged→abandoned."""
    if pr.get("merged_at") or pr.get("merged"):
        return "implemented"
    state = (pr.get("state") or "").lower()
    if state == "open":
        return "started"
    return "abandoned"


# ── Fetch + assemble ─────────────────────────────────────────────────────────


def _paged(fetch: Callable[[int], list[dict]], *, max_pages: int) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = fetch(page)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return out


def parse_repo(
    repo: str,
    *,
    token: str = "",
    gh_get: Callable[..., Any] = _gh_get,
    per_page: int = PER_PAGE,
    max_pages: int = MAX_PAGES,
) -> RepoHistoryMap:
    """Fetch issues (state=all, PRs filtered out) and pull requests for ``repo``
    ("owner/name") and classify every item into a RepoHistoryMap."""
    m = RepoHistoryMap(repo=repo)

    def _issues(page: int) -> list[dict]:
        return gh_get(
            f"/repos/{repo}/issues",
            params={"state": "all", "per_page": per_page, "page": page},
            token=token,
        ) or []

    def _pulls(page: int) -> list[dict]:
        return gh_get(
            f"/repos/{repo}/pulls",
            params={"state": "all", "per_page": per_page, "page": page},
            token=token,
        ) or []

    for issue in _paged(_issues, max_pages=max_pages):
        if is_pull_request(issue):
            continue  # counted via the /pulls sweep, which carries merge state
        m.items.append(
            WorkItem(
                kind="issue",
                number=int(issue.get("number", 0)),
                title=str(issue.get("title", "")),
                status=classify_issue(issue),
                url=str(issue.get("html_url", "")),
                updated_at=str(issue.get("updated_at", "")),
            )
        )
    for pr in _paged(_pulls, max_pages=max_pages):
        m.items.append(
            WorkItem(
                kind="pr",
                number=int(pr.get("number", 0)),
                title=str(pr.get("title", "")),
                status=classify_pr(pr),
                url=str(pr.get("html_url", "")),
                updated_at=str(pr.get("updated_at", "")),
            )
        )
    return m


# ── Render ───────────────────────────────────────────────────────────────────


def render_map(m: RepoHistoryMap) -> str:
    counts = m.counts()
    lines = [f"# {m.repo} — history map ({len(m.items)} items)"]
    for status in STATUS_ORDER:
        lines.append(f"- {status}: {counts[status]}")
    return "\n".join(lines)
