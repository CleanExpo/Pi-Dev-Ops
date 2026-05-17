"""Shared Linear GraphQL helpers. Extracted from scripts/process_ideas_inbox.py:49-93
to support both the existing ideas-inbox flow and the new plaud-actions flow.

process_ideas_inbox.py is NOT modified — it keeps its own copy of the function
to avoid coupling unrelated work. Both call sites talk to the same Linear API
and behave identically; this module is the canonical pattern for new callers.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("linear_helpers")

LINEAR_API_URL = "https://api.linear.app/graphql"
ISSUE_CREATE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url }
  }
}
"""


@dataclass
class TicketRef:
    """A reference to a successfully created Linear ticket."""
    id: str            # Linear internal UUID
    identifier: str    # human-readable, e.g. "CCW-247"
    url: str = ""      # canonical Linear URL (may be empty for older API responses)


def create_linear_issue(
    *,
    api_key: str,
    title: str,
    description: str,
    team_id: str,
    project_id: str,
    priority: int = 3,
) -> Optional[TicketRef]:
    """POST to Linear GraphQL to create an issue. Returns TicketRef or None.

    priority: Linear scale — 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low.
    title is truncated to 250 chars (Linear's cap).
    """
    variables = {"input": {
        "teamId": team_id,
        "projectId": project_id,
        "title": title[:250],
        "description": description,
        "priority": priority,
    }}
    payload = json.dumps({"query": ISSUE_CREATE_MUTATION, "variables": variables}).encode()

    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        log.warning("create_linear_issue HTTP failure: %s", exc)
        return None

    if "errors" in data:
        log.warning("create_linear_issue GraphQL errors: %s", data["errors"])
        return None

    result = data.get("data", {}).get("issueCreate", {}) or {}
    if not result.get("success"):
        log.warning("create_linear_issue not successful: %s", result)
        return None

    issue = result.get("issue") or {}
    return TicketRef(
        id=issue.get("id", ""),
        identifier=issue.get("identifier", ""),
        url=issue.get("url", ""),
    )
