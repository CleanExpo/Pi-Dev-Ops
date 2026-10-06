"""The autonomy poller's portfolio queue read (RA-7931).

The poller used to read every portfolio project once per autonomy label
(15 x 2 = 30+ Linear requests every 300 s poll, ~360+/h of the fleet key's
2,500/h). ``portfolio_issues`` reads the whole Ready queue in one paginated
``TODO_ISSUES_QUERY`` and maps each node back to its registry row.
"""
from __future__ import annotations

from collections.abc import Callable

from app.server.autonomy_queue import issue_pages


def portfolio_issues(gql: Callable[..., dict], api_key: str, projects: list[dict],
                     status_name: str, labels: tuple[str, ...]) -> list[dict]:
    """The whole Ready queue of every portfolio project, annotated, deduped by id.

    One paginated read (RA-7931), not one per project x label. Each node is mapped
    back to its registry row by ``project { id }``; the first row registered for a
    project id wins, as the per-project loop's iteration order did. Raises on any
    failed or partial page: the caller never sees a part of the queue.
    """
    rows: dict[str, dict] = {}
    for p in projects:
        rows.setdefault(p["project_id"], p)
    if not rows:
        return []
    seen: set[str] = set()
    merged: list[dict] = []
    for issue in issue_pages(gql, api_key, {
        "projectIds": list(rows), "statusName": status_name, "labelNames": list(labels),
    }):
        iid = issue.get("id")
        p = rows.get(((issue.get("project") or {}).get("id")) or "")
        if not iid or iid in seen or p is None:
            continue
        seen.add(iid)
        issue["_repo_url"] = p["repo_url"]
        issue["_team_id"] = p["team_id"]
        issue["_project_name"] = p["name"]
        issue["_project_id"] = p["project_id"]
        merged.append(issue)
    return merged
