"""Vercel webhook → Outcome.

Handles:
  deployment.succeeded  → metric='deploy_success', value_numeric=1.0
  deployment.error      → metric='deploy_error',   value_numeric=1.0

Workspace attribution: payload.team.id maps to workspace via the
client_workspaces.vercel_project lookup; for now we accept it as the
slug directly. Future B5 wires the lookup.
"""
from __future__ import annotations

from typing import Any

from ..types import Outcome
from . import ParseResult, make_outcome_id, safe_str
from .workspace_resolver import WorkspaceLookup, resolve_workspace

HANDLED_TYPES = {"deployment.succeeded", "deployment.error"}


def parse(
    body: dict[str, Any],
    *,
    captured_at: str,
    lookup: WorkspaceLookup | None = None,
) -> ParseResult:
    if not isinstance(body, dict):
        return ParseResult(result="malformed", reason="body is not an object")

    event_id = safe_str(body.get("id"))
    event_type = safe_str(body.get("type"))
    if not event_id:
        return ParseResult(result="malformed", reason="missing event id")
    if event_type not in HANDLED_TYPES:
        return ParseResult(result="ignored", event_id=event_id,
                           reason=f"event type {event_type!r} not handled")

    payload = body.get("payload") or {}
    workspace_slug = safe_str(payload.get("workspace_slug"))
    workspace_id = safe_str(payload.get("workspace_id"))
    if (not workspace_slug or not workspace_id) and lookup is not None:
        project_id = safe_str((payload.get("project") or {}).get("id"))
        resolved = resolve_workspace("vercel", project_id, lookup)
        if resolved is not None:
            workspace_id, workspace_slug = resolved
    if not workspace_slug or not workspace_id:
        return ParseResult(
            result="malformed", event_id=event_id,
            reason="workspace attribution missing: provide payload.workspace_slug + workspace_id, OR map vercel project id to client_workspaces.vercel_project",
        )

    metric = "deploy_success" if event_type == "deployment.succeeded" else "deploy_error"
    outcome = Outcome(
        id=make_outcome_id("vercel", event_id),
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        source="vercel",
        metric=metric,
        captured_at=captured_at,
        value_numeric=1.0,
        value_text=safe_str((payload.get("deployment") or {}).get("url")) or None,
        raw_payload={"id": event_id, "type": event_type},
    )
    return ParseResult(result="ok", event_id=event_id, outcome=outcome)
