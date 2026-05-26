"""Linear webhook → Outcome.

Handles Issue.completed (state transitions from any non-completed to
'completed'). Workspace attribution: payload.workspaceSlug or
payload.data.team.key mapped via the workspace.linear_team_id field
in client_workspaces.

For B4 the parser expects callers to provide workspace_slug +
workspace_id directly in the payload (the route handler will look
them up against client_workspaces in a follow-up; for now we keep
the parser pure-logic).
"""
from __future__ import annotations

from typing import Any

from ..types import Outcome
from . import ParseResult, make_outcome_id, safe_str


def parse(body: dict[str, Any], *, captured_at: str) -> ParseResult:
    if not isinstance(body, dict):
        return ParseResult(result="malformed", reason="body is not an object")

    delivery_id = safe_str(body.get("deliveryId"))
    event_type = safe_str(body.get("type"))
    action = safe_str(body.get("action"))
    if not delivery_id:
        return ParseResult(result="malformed", reason="missing deliveryId")

    if event_type != "Issue" or action != "update":
        return ParseResult(result="ignored", event_id=delivery_id,
                           reason=f"type/action {event_type!r}/{action!r} not handled")

    data = body.get("data") or {}
    state = (data.get("state") or {}).get("type", "")
    if state != "completed":
        return ParseResult(result="ignored", event_id=delivery_id,
                           reason="issue state is not 'completed'")

    workspace_slug = safe_str(body.get("workspace_slug"))
    workspace_id = safe_str(body.get("workspace_id"))
    if not workspace_slug or not workspace_id:
        return ParseResult(
            result="malformed", event_id=delivery_id,
            reason="workspace_slug + workspace_id required at body root",
        )

    outcome = Outcome(
        id=make_outcome_id("linear", delivery_id),
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source="linear",
        metric="issue_completion",
        captured_at=captured_at,
        value_numeric=1.0,
        value_text=safe_str(data.get("title")) or None,
        raw_payload={"deliveryId": delivery_id, "issue_id": safe_str(data.get("id"))},
    )
    return ParseResult(result="ok", event_id=delivery_id, outcome=outcome)
