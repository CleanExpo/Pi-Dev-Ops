"""
linear_pulse_rotate.py — keep the 15-min pulse alive past Linear's per-issue comment cap.

Linear refuses a comment once an issue holds 2000 (QUOTA_EXCEEDED, quota
`max-comments-per-issue`). At four pulses an hour one issue fills in about three weeks;
RA-7391 filled on ~15 Sept 2026 and every pulse after that was refused. When that exact
refusal arrives, open a fresh pulse issue that links the full one, and post there.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("pi-ceo.linear_pulse")

_CREATE = """
mutation($input: IssueCreateInput!) {
  issueCreate(input: $input) { success issue { id identifier url } }
}
"""


def is_comment_quota_error(errors: list | None) -> bool:
    """True only for Linear's per-issue comment cap, never for other refusals."""
    for err in errors or []:
        ext = (err or {}).get("extensions") or {}
        quota = (ext.get("meta") or {}).get("quota")
        if ext.get("code") == "QUOTA_EXCEEDED" and quota == "max-comments-per-issue":
            return True
    return False


def create_pulse_issue(state: dict, title: str, previous_id: str | None = None) -> str | None:
    """Create a pulse issue, cache its id in `state`, and return it."""
    from . import linear_pulse as lp

    team_id = os.environ.get("LINEAR_PULSE_TEAM_ID") or os.environ.get("LINEAR_TEAM_ID")
    project_id = os.environ.get("LINEAR_PULSE_PROJECT_ID") or os.environ.get("LINEAR_PROJECT_ID")
    if not team_id:
        return None
    description = (
        "Auto-created by Pi-CEO linear_pulse. Receives a comment every 15 min with the "
        "current portfolio snapshot.\n\nDo not close — system will recreate if missing."
    )
    if previous_id:
        description += (
            f"\n\nContinues pulse issue `{previous_id}`, which reached Linear's "
            "2000-comment limit per issue."
        )
    inp = {"teamId": team_id, "title": title, "description": description, "priority": 0}
    if project_id:
        inp["projectId"] = project_id
    issue = ((lp._graphql(_CREATE, {"input": inp}) or {}).get("issueCreate") or {}).get("issue")
    if not issue:
        log.warning("linear_pulse: failed to create pulse issue")
        return None
    state["pulse_issue_id"] = issue.get("id")
    lp._save_state(state)
    return state["pulse_issue_id"]


def _rotate(state: dict, full_id: str) -> str | None:
    from . import linear_pulse as lp

    state.setdefault("retired_pulse_issue_ids", []).append(full_id)
    state.pop("pulse_issue_id", None)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return create_pulse_issue(state, f"{lp._PULSE_ISSUE_TITLE} — from {day}", full_id)


def post_portfolio_pulse(state: dict) -> bool:
    """Post the digest to the pulse issue, rotating once if that issue is full."""
    from . import linear_pulse as lp

    pulse_id = lp._pulse_issue_id(state)
    if not pulse_id:
        return False
    try:
        from .digest import render_digest_text

        body = render_digest_text()
    except Exception as exc:  # noqa: BLE001
        body = f"digest unavailable: {exc}"
    lp._last_errors = []
    if lp._post_comment(pulse_id, body):
        return True
    if is_comment_quota_error(lp._last_errors):
        new_id = _rotate(state, pulse_id)
        if new_id and lp._post_comment(new_id, body):
            log.warning("linear_pulse: pulse issue %s is full; moved to %s", pulse_id, new_id)
            return True
    log.error(
        "linear_pulse: portfolio-pulse comment FAILED to post to issue=%s — "
        "the 15-min heartbeat did not reach Linear this tick",
        pulse_id,
    )
    return False
