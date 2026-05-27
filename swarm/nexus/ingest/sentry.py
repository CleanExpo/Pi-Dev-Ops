"""Sentry webhook → Outcome.

Handles 'event_alert' issue events. Payload shape (simplified):

  {
    "id": "<delivery-id>",
    "action": "created" | "resolved",
    "data": {
      "issue": {
        "id": "...",
        "title": "...",
        "level": "error" | "warning",
        "metadata": {
          "workspace_slug": "...",
          "workspace_id": "..."
        }
      }
    }
  }
"""
from __future__ import annotations

from typing import Any

from ..types import Outcome
from . import ParseResult, make_outcome_id, safe_str
from .workspace_resolver import WorkspaceLookup  # noqa: F401 — kept for signature parity

HANDLED_ACTIONS = {"created", "resolved"}


def parse(
    body: dict[str, Any],
    *,
    captured_at: str,
    lookup: WorkspaceLookup | None = None,  # noqa: ARG001 — kept for signature parity
) -> ParseResult:
    if not isinstance(body, dict):
        return ParseResult(result="malformed", reason="body is not an object")

    delivery_id = safe_str(body.get("id"))
    action = safe_str(body.get("action"))
    if not delivery_id:
        return ParseResult(result="malformed", reason="missing delivery id")
    if action not in HANDLED_ACTIONS:
        return ParseResult(result="ignored", event_id=delivery_id,
                           reason=f"action {action!r} not handled")

    issue = ((body.get("data") or {}).get("issue") or {})
    metadata = issue.get("metadata") or {}
    workspace_slug = safe_str(metadata.get("workspace_slug"))
    workspace_id = safe_str(metadata.get("workspace_id"))
    if not workspace_slug or not workspace_id:
        return ParseResult(
            result="malformed", event_id=delivery_id,
            reason="issue.metadata.workspace_slug + workspace_id required",
        )

    metric = "error_rate_spike" if action == "created" else "error_resolved"
    outcome = Outcome(
        id=make_outcome_id("sentry", delivery_id),
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source="sentry",
        metric=metric,
        captured_at=captured_at,
        value_numeric=1.0,
        value_text=safe_str(issue.get("title")) or None,
        delta_window="24h",
        raw_payload={"id": delivery_id, "action": action, "level": safe_str(issue.get("level"))},
    )
    return ParseResult(result="ok", event_id=delivery_id, outcome=outcome)
