"""
session_linear.py — Linear two-way sync helpers for build sessions.

Extracted from sessions.py (RA-890). Contains all Linear GraphQL calls and
session-outcome recording:

  - _update_linear_state()       — move an issue to a named workflow state
  - _post_linear_comment()       — append a comment to a Linear issue
  - _record_session_outcome()    — write JSONL row to .harness/session-outcomes.jsonl
  - _sync_linear_on_completion() — orchestrate state+comment on terminal status

Import graph:
  session_linear  →  config
  No session_model / session_sdk / session_evaluator imports (leaf node).

Public API (re-exported by sessions.py for backward compatibility):
  All four functions above.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config

_log = logging.getLogger("pi-ceo.session_linear")


# ── GraphQL helpers ────────────────────────────────────────────────────────────

def _update_linear_state(issue_id: str, state_name: str) -> None:
    """Move a Linear issue to the named workflow state.

    Uses urllib only (no extra dependencies).  Never raises — failures are
    logged and silently swallowed so a Linear outage cannot break a build.

    Algorithm:
      1. Fetch the issue's team ID and current state ID.
      2. List the team's workflow states and find the ID whose name matches
         state_name (case-insensitive).
      3. Call updateIssue mutation with the resolved state ID.
    """
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        _log.warning("LINEAR_API_KEY not set — cannot update Linear issue %s to '%s'", issue_id, state_name)
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": api_key,
    }

    def _gql(query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        # Step 1: get team ID for the issue
        fetch_q = """
query GetIssueTeam($id: String!) {
  issue(id: $id) {
    team { id }
  }
}"""
        result = _gql(fetch_q, {"id": issue_id})
        team_id = (result.get("data") or {}).get("issue", {}).get("team", {}).get("id")
        if not team_id:
            _log.warning("Linear: could not resolve team for issue %s — skipping state update", issue_id)
            return

        # Step 2: find the workflow state ID whose name matches state_name
        states_q = """
query GetTeamStates($teamId: String!) {
  team(id: $teamId) {
    states { nodes { id name type } }
  }
}"""
        result = _gql(states_q, {"teamId": team_id})
        nodes = (result.get("data") or {}).get("team", {}).get("states", {}).get("nodes", [])
        target_id = None
        for node in nodes:
            if node.get("name", "").lower() == state_name.lower():
                target_id = node["id"]
                break
        if not target_id:
            _log.warning(
                "Linear: state '%s' not found in team %s — available: %s",
                state_name, team_id, [n.get("name") for n in nodes],
            )
            return

        # Step 3: update the issue
        mutation = """
mutation UpdateIssueState($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) {
    success
    issue { id title state { name } }
  }
}"""
        result = _gql(mutation, {"id": issue_id, "stateId": target_id})
        success = (result.get("data") or {}).get("issueUpdate", {}).get("success", False)
        if success:
            _log.info("Linear: issue %s moved to '%s'", issue_id, state_name)
        else:
            errors = result.get("errors") or []
            _log.warning("Linear: issueUpdate returned success=false for %s — errors: %s", issue_id, errors)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        _log.warning("Linear HTTP %s updating issue %s to '%s': %s", exc.code, issue_id, state_name, body)
    except Exception as exc:
        _log.warning("Linear update failed for issue %s to '%s': %s", issue_id, state_name, exc)


def _post_linear_comment(issue_id: str, body: str) -> None:
    """Post a comment to a Linear issue. Never raises — failures are logged and swallowed."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return
    mutation = """
mutation PostComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
  }
}"""
    payload = json.dumps({"query": mutation, "variables": {"issueId": issue_id, "body": body}}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if not (result.get("data") or {}).get("commentCreate", {}).get("success"):
                _log.warning("Linear: commentCreate returned success=false for issue %s", issue_id)
    except Exception as exc:
        _log.warning("Linear comment failed for issue %s: %s", issue_id, exc)


# ── Session outcome recording ──────────────────────────────────────────────────

def _record_session_outcome(session, push_ok: bool, push_ts: float) -> None:
    """RA-672 Phase 2 — Write session outcome to .harness/session-outcomes.jsonl.

    Feeds ZTE v2 C2 (output acceptance) scoring in zte_v2_score.py.
    Each line: session_id, linear_issue_id, push_ok, push_timestamp,
    linear_state_after, completed_at.
    """
    _harness_dir = Path(config.DATA_DIR).parent.parent / ".harness"
    outcomes_file = _harness_dir / "session-outcomes.jsonl"
    _harness_dir.mkdir(parents=True, exist_ok=True)

    # Record Linear state after push — session moves issue to "In Review" on push.
    # The downstream board meeting / autonomy poller moves it to Done after human review.
    # For C2 scoring we capture "In Review" as the immediate post-push state.
    issue_id = getattr(session, "linear_issue_id", None)
    linear_state_after = "In Review" if (issue_id and push_ok) else ""

    row = {
        "session_id": session.id,
        "linear_issue_id": issue_id,
        "push_ok": push_ok,
        "push_timestamp": datetime.fromtimestamp(push_ts, tz=timezone.utc).isoformat() if push_ok else None,
        "linear_state_after": linear_state_after,
        "session_status": getattr(session, "status", ""),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(outcomes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError as exc:
        _log.warning("Could not write session-outcomes.jsonl: %s", exc)


def _sync_linear_on_completion(session) -> None:
    """RA-665/666 — Post build outcome to Linear on every terminal state.

    Called from run_build() finally block so it fires on success AND all
    early-return failure paths without touching each individual return.
    """
    issue_id = getattr(session, "linear_issue_id", None)
    if not issue_id:
        return
    status = getattr(session, "status", "")
    duration_s = int(time.time() - (session.started_at or time.time()))
    eval_score = getattr(session, "evaluator_score", None)
    eval_status = getattr(session, "evaluator_status", "")

    if status == "complete":
        score_line = f"Evaluator: {eval_score}/10 ({eval_status})\n" if eval_score else ""
        comment = (
            f"Pi CEO build **complete** in {duration_s}s.\n\n"
            f"{score_line}"
            f"Session: `{session.id}`"
        )
        _post_linear_comment(issue_id, comment)
        # Issue already moved to "In Review" during push phase; leave it there
        # so a human can review the PR before marking Done.
    elif status == "failed":
        comment = (
            f"Pi CEO build **failed** after {duration_s}s.\n\n"
            f"Session: `{session.id}` — check Railway logs for details."
        )
        _post_linear_comment(issue_id, comment)
        # Move back to Todo so the issue is visible as needing attention
        _update_linear_state(issue_id, "Todo")
    # killed / other terminal states: no Linear update needed
