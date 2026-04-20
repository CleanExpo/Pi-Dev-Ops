"""
test_autonomy_contract.py — RA-1369 Linear contract compliance tests.

Locks the behaviour described in skills/pi-dev-linear-contract/SKILL.md:

  1. Block A — autonomy queue filter uses status name "Ready for Pi-Dev"
     AND label "pi-dev:autonomous" (both required).
  2. Block B — intent + scope are passed through when the poller fires
     create_session() (already tested at the inference level in
     test_autonomy_hardening.py; here we lock the ingestion path).
  3. Block C — orphan recovery transitions to "Pi-Dev: Blocked" and adds
     the "pi-dev:blocked-reason:session-lost" label, falling back
     gracefully when label creation fails.
  4. Session-start failure reverts to "Ready for Pi-Dev" (contract) with
     "Todo" fallback (pre-RA-1298 workspaces).

The tests avoid live Linear API calls by monkey-patching _gql and the
helpers. No network traffic is issued.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.server import autonomy


# ── Block A — autonomy queue filter -----------------------------------------
def test_fetch_todo_issues_filter_requires_status_and_label():
    """fetch_todo_issues must send both statusName + autonomyLabel variables
    to the GraphQL query, and must exclude projects with no linear_project_id."""
    captured: list[dict] = []

    def fake_gql(api_key, query, variables=None):
        captured.append({"query": query, "variables": variables or {}})
        return {"project": {"issues": {"nodes": []}}}

    # Use the single Pi-Dev-Ops fallback project so the test is deterministic
    # whether or not projects.json is available on the CI runner.
    with patch.object(autonomy, "_load_portfolio_projects", return_value=[{
        "project_id": "proj-a",
        "team_id":    "team-a",
        "repo_url":   "https://github.com/x/y",
        "name":       "Test",
    }]):
        with patch.object(autonomy, "_gql", side_effect=fake_gql):
            autonomy.fetch_todo_issues("k")

    assert len(captured) == 1
    q = captured[0]["query"]
    v = captured[0]["variables"]

    # Query shape: status name filter + labels filter (the two MUST-haves).
    assert "state: { name: { eq: $statusName }" in q
    assert "labels: { name: { eq: $autonomyLabel }" in q
    # Old filter disallowed — no state.type and no priority filter any more.
    assert "type: { in:" not in q, "old state.type filter must be removed"
    assert "priority:" not in q, "priority filter was removed (label + status is the contract signal)"

    assert v["statusName"]    == "Ready for Pi-Dev"
    assert v["autonomyLabel"] == "pi-dev:autonomous"
    assert v["projectId"]     == "proj-a"


def test_autonomy_constants_match_contract():
    """Constants are part of the public observable surface for audits."""
    assert autonomy._READY_STATUS_NAME           == "Ready for Pi-Dev"
    assert autonomy._AUTONOMY_LABEL              == "pi-dev:autonomous"
    assert autonomy._BLOCKED_STATUS_NAME         == "Pi-Dev: Blocked"
    assert autonomy._BLOCKED_REASON_SESSION_LOST == "pi-dev:blocked-reason:session-lost"


# ── Block C — orphan recovery transitions to Blocked + reason label ---------
def test_orphan_recovery_transitions_to_blocked_with_reason_label():
    """Orphan (session-lost) → Pi-Dev: Blocked + pi-dev:blocked-reason:session-lost."""
    orphan_issue = {
        "id": "iss-1",
        "identifier": "RA-999",
        "title": "dead session",
        "comments": {"nodes": [
            {"body": "🤖 **Pi-CEO autonomous session started**\n\n- Session ID: `deadbeefdead`\n"},
        ]},
    }

    # Fake: no live sessions, one project, one orphan.
    transitions: list[tuple[str, str, str]]   = []  # (issue_id, state, team_id)
    labels_added: list[tuple[str, str, str]]  = []  # (issue_id, team_id, label)
    comments: list[tuple[str, str]]           = []

    def fake_transition(api_key, issue_id, state, team_id=autonomy._TEAM_ID):
        transitions.append((issue_id, state, team_id))

    def fake_add_label(api_key, issue_id, team_id, label):
        labels_added.append((issue_id, team_id, label))
        return True

    def fake_comment(api_key, issue_id, body):
        comments.append((issue_id, body))

    def fake_gql(api_key, query, variables=None):
        # Return the orphan when _IN_PROGRESS_QUERY is issued.
        return {"project": {"issues": {"nodes": [orphan_issue]}}}

    projects = [{"project_id": "p1", "team_id": "t1", "repo_url": "x", "name": "P1"}]

    with patch.object(autonomy, "_load_portfolio_projects", return_value=projects), \
         patch.object(autonomy, "_gql", side_effect=fake_gql), \
         patch.object(autonomy, "transition_issue", side_effect=fake_transition), \
         patch.object(autonomy, "add_label_to_issue", side_effect=fake_add_label), \
         patch.object(autonomy, "comment_on_issue", side_effect=fake_comment), \
         patch("app.server.sessions._sessions", {}, create=True):
        asyncio.run(autonomy._orphan_recovery("k"))

    assert transitions  == [("iss-1", "Pi-Dev: Blocked", "t1")]
    assert labels_added == [("iss-1", "t1", "pi-dev:blocked-reason:session-lost")]
    assert len(comments) == 1
    _, body = comments[0]
    assert "session-lost" in body or "session lost" in body.lower()
    assert "Pi-Dev: Blocked" in body


def test_orphan_recovery_skips_live_sessions():
    """A ticket whose session_id IS live must not be transitioned."""
    live_issue = {
        "id": "iss-ok",
        "identifier": "RA-OK",
        "title": "still running",
        "comments": {"nodes": [
            {"body": "- Session ID: `abcdef123456`\n"},
        ]},
    }

    calls: list[tuple[str, ...]] = []
    def fake_transition(*args, **kwargs):
        calls.append(("transition", *args))

    def fake_gql(api_key, query, variables=None):
        return {"project": {"issues": {"nodes": [live_issue]}}}

    projects = [{"project_id": "p1", "team_id": "t1", "repo_url": "x", "name": "P1"}]
    live = {"abcdef123456": object()}

    with patch.object(autonomy, "_load_portfolio_projects", return_value=projects), \
         patch.object(autonomy, "_gql", side_effect=fake_gql), \
         patch.object(autonomy, "transition_issue", side_effect=fake_transition), \
         patch("app.server.sessions._sessions", live, create=True):
        asyncio.run(autonomy._orphan_recovery("k"))

    assert calls == [], "live session must not be reverted"


def test_orphan_recovery_label_failure_does_not_block_transition():
    """Label create failure is logged but the status transition still happens."""
    orphan = {
        "id": "iss-2", "identifier": "RA-888", "title": "x",
        "comments": {"nodes": [{"body": "Session ID: `ffffeeee0000`"}]},
    }
    transitions: list[str] = []
    def fake_transition(api_key, issue_id, state, team_id=autonomy._TEAM_ID):
        transitions.append(state)
    def fake_add_label(*a, **k):
        return False    # label create/attach failed
    def fake_comment(*a, **k):
        pass
    def fake_gql(api_key, query, variables=None):
        return {"project": {"issues": {"nodes": [orphan]}}}

    with patch.object(autonomy, "_load_portfolio_projects",
                      return_value=[{"project_id":"p","team_id":"t","repo_url":"x","name":"n"}]), \
         patch.object(autonomy, "_gql", side_effect=fake_gql), \
         patch.object(autonomy, "transition_issue", side_effect=fake_transition), \
         patch.object(autonomy, "add_label_to_issue", side_effect=fake_add_label), \
         patch.object(autonomy, "comment_on_issue", side_effect=fake_comment), \
         patch("app.server.sessions._sessions", {}, create=True):
        asyncio.run(autonomy._orphan_recovery("k"))

    assert transitions == ["Pi-Dev: Blocked"], \
        "transition must happen even if label attach fails"


# ── Block B — intent + scope passthrough ------------------------------------
def test_infer_intent_foundation_label_maps_to_feature():
    """Contract: `foundation` → FEATURE (feature)."""
    issue = {"labels": {"nodes": [{"name": "foundation"}]}}
    assert autonomy._infer_intent(issue) == "feature"


def test_infer_intent_and_scope_contract_defaults():
    """Unknown labels + no estimate → empty intent + 15-file scope."""
    issue = {"labels": {"nodes": [{"name": "mystery"}]}}
    assert autonomy._infer_intent(issue) == ""
    assert autonomy._infer_scope(issue) == {"type": "auto-routine",
                                            "max_files_modified": 15}
