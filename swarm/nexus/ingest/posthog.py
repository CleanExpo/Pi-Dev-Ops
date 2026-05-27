"""PostHog webhook → Outcome.

Handles funnel conversion events. We expect a payload shaped like:

  {
    "id": "<event-id>",
    "event": "funnel_completed" | "funnel_dropped",
    "properties": {
      "workspace_slug": "...",
      "workspace_id": "...",
      "funnel_name": "...",
      "conversion_rate": 0.42
    }
  }
"""
from __future__ import annotations

from typing import Any

from ..types import Outcome
from . import ParseResult, make_outcome_id, safe_float, safe_str
from .workspace_resolver import WorkspaceLookup  # noqa: F401 — kept for signature parity

HANDLED_EVENTS = {"funnel_completed", "funnel_dropped"}


def parse(
    body: dict[str, Any],
    *,
    captured_at: str,
    lookup: WorkspaceLookup | None = None,  # noqa: ARG001 — kept for signature parity
) -> ParseResult:
    if not isinstance(body, dict):
        return ParseResult(result="malformed", reason="body is not an object")

    event_id = safe_str(body.get("id"))
    event = safe_str(body.get("event"))
    if not event_id:
        return ParseResult(result="malformed", reason="missing event id")
    if event not in HANDLED_EVENTS:
        return ParseResult(result="ignored", event_id=event_id,
                           reason=f"event {event!r} not handled")

    props = body.get("properties") or {}
    workspace_slug = safe_str(props.get("workspace_slug"))
    workspace_id = safe_str(props.get("workspace_id"))
    if not workspace_slug or not workspace_id:
        return ParseResult(
            result="malformed", event_id=event_id,
            reason="properties.workspace_slug + workspace_id required",
        )

    metric = "funnel_conversion_rate"
    outcome = Outcome(
        id=make_outcome_id("posthog", event_id),
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source="posthog",
        metric=metric,
        captured_at=captured_at,
        value_numeric=safe_float(props.get("conversion_rate")),
        value_text=safe_str(props.get("funnel_name")) or None,
        raw_payload={"id": event_id, "event": event},
    )
    return ParseResult(result="ok", event_id=event_id, outcome=outcome)
