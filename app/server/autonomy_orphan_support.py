"""Pagination helpers for safe orphan-recovery retries."""

from .autonomy_orphan_queries import _COMMENT_PAGE_QUERY


def recovery_comment_present(issue: dict, gql, api_key: str, marker: str) -> bool:
    connection = issue.get("comments") or {}
    seen_cursors: set[str] = set()
    while True:
        if any(marker in (node.get("body") or "")
               for node in connection.get("nodes") or []):
            return True
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return False
        cursor = page_info.get("endCursor")
        if not cursor or cursor in seen_cursors:
            raise RuntimeError("Linear comment pagination did not advance")
        seen_cursors.add(cursor)
        data = gql(api_key, _COMMENT_PAGE_QUERY,
                   {"issueId": issue["id"], "after": cursor})
        connection = (data.get("issue") or {}).get("comments") or {}


def issue_pages(gql, api_key: str, query: str, variables: dict,
                *, paginate: bool):
    """Yield target-state pages; started-state scans retain their original bound."""
    seen_cursors: set[str] = set()
    pages: list[list[dict]] = []
    while True:
        data = gql(api_key, query, variables)
        connection = (data.get("project") or {}).get("issues") or {}
        pages.append(connection.get("nodes") or [])
        page_info = connection.get("pageInfo") or {}
        if not paginate or not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor or cursor in seen_cursors:
            raise RuntimeError("Linear issue pagination did not advance")
        seen_cursors.add(cursor)
        variables = {**variables, "after": cursor}
    for page in pages:
        yield page


def orphan_completion(issue: dict, label_name: str, marker: str) -> tuple[bool, bool]:
    labels = (issue.get("labels") or {}).get("nodes") or []
    comments = (issue.get("comments") or {}).get("nodes") or []
    labelled = any(n.get("name") == label_name for n in labels)
    commented = any(marker in (n.get("body") or "") for n in comments)
    return labelled, commented


def record_recovery_success(log_event, pending: set[str], iid: str, ident: str,
                            target: str, reason: str, label_ok: bool) -> None:
    log_event({"action": "orphan_recovered", "ticket": ident,
               "transition": target, "reason_label": reason,
               "label_attached": label_ok})
    pending.discard(iid)


def transition_orphan_issue(transition_issue, log_event, log, api_key: str,
                            iid: str, ident: str, team_id: str, target: str) -> bool:
    try:
        transition_issue(api_key, iid, target, team_id=team_id)
    except RuntimeError as exc:
        if "not found" not in str(exc).lower():
            raise
        log.warning("orphan-recovery: state '%s' missing on team %s for %s — skipping",
                    target, team_id, ident)
        log_event({"action": "orphan_recovery_state_missing", "ticket": ident,
                   "team_id": team_id, "target_state": target, "error": str(exc)})
        return False
    return True
