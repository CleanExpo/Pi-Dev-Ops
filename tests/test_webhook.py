"""
test_webhook.py — Unit tests for GitHub and Linear webhook signature verification.
"""
import hashlib
import hmac

from app.server.webhook import (
    verify_github_signature,
    verify_linear_signature,
    parse_github_event,
    parse_linear_event,
    linear_issue_to_brief,
)


SECRET = "test-webhook-secret"


def _github_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _linear_sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── GitHub signature ──────────────────────────────────────────────────────────

def test_github_sig_valid():
    body = b'{"action":"opened"}'
    sig = _github_sig(body, SECRET)
    assert verify_github_signature(body, sig, SECRET) is True


def test_github_sig_wrong_secret():
    body = b'{"action":"opened"}'
    sig = _github_sig(body, SECRET)
    assert verify_github_signature(body, sig, "wrong-secret") is False


def test_github_sig_tampered_body():
    body = b'{"action":"opened"}'
    sig = _github_sig(body, SECRET)
    assert verify_github_signature(b'{"action":"closed"}', sig, SECRET) is False


def test_github_sig_empty_secret():
    body = b'data'
    sig = _github_sig(body, SECRET)
    assert verify_github_signature(body, sig, "") is False


def test_github_sig_empty_signature():
    body = b'data'
    assert verify_github_signature(body, "", SECRET) is False


# ── Linear signature ──────────────────────────────────────────────────────────

def test_linear_sig_valid():
    body = b'{"type":"Issue"}'
    sig = _linear_sig(body, SECRET)
    assert verify_linear_signature(body, sig, SECRET) is True


def test_linear_sig_wrong_secret():
    body = b'{"type":"Issue"}'
    sig = _linear_sig(body, SECRET)
    assert verify_linear_signature(body, sig, "wrong") is False


def test_linear_sig_empty_inputs():
    assert verify_linear_signature(b"data", "", SECRET) is False
    assert verify_linear_signature(b"data", "sig", "") is False


# ── GitHub event parsing ──────────────────────────────────────────────────────

def test_parse_github_push():
    payload = {"repository": {"html_url": "https://github.com/org/repo"}, "ref": "refs/heads/main"}
    event = parse_github_event("push", payload)
    assert event is not None
    assert event["repo_url"] == "https://github.com/org/repo"
    assert event["event"] == "push"
    assert event["ref"] == "refs/heads/main"


def test_parse_github_pull_request():
    payload = {
        "repository": {"html_url": "https://github.com/org/repo"},
        "action": "opened",
        "number": 42,
    }
    event = parse_github_event("pull_request", payload)
    assert event is not None
    assert event["repo_url"] == "https://github.com/org/repo"


def test_parse_github_unsupported_event():
    assert parse_github_event("ping", {}) is None
    assert parse_github_event("delete", {}) is None


def test_parse_github_missing_repo():
    assert parse_github_event("push", {}) is None
    assert parse_github_event("push", {"repository": {}}) is None


# ── Linear event parsing ──────────────────────────────────────────────────────

def test_parse_linear_issue_started():
    payload = {
        "type": "Issue",
        "action": "update",
        "updatedFrom": {"stateId": "prev-state-id"},  # required: signals state changed
        "data": {
            "id": "abc-123",
            "title": "Fix auth bug",
            "state": {"name": "In Progress", "type": "started"},  # Linear state type
            "description": "repo:https://github.com/org/repo\nFix the bug",
        },
    }
    event = parse_linear_event(payload)
    assert event is not None
    assert event["title"] == "Fix auth bug"
    assert event["repo_url"] == "https://github.com/org/repo"


def test_parse_linear_non_issue():
    assert parse_linear_event({"type": "Comment", "action": "create", "data": {}}) is None


def test_parse_linear_non_started_state():
    payload = {
        "type": "Issue",
        "action": "update",
        "data": {
            "id": "abc",
            "title": "Some issue",
            "state": {"name": "Backlog"},
            "description": "",
        },
    }
    assert parse_linear_event(payload) is None


def test_parse_linear_update_without_state_change_skipped():
    # RA-6787 gap: an update whose diff does not touch stateId must be ignored,
    # even if the current state happens to be "started".
    payload = {
        "type": "Issue",
        "action": "update",
        "updatedFrom": {"title": "old title"},  # no stateId → not a transition
        "data": {
            "id": "abc",
            "title": "Renamed issue",
            "state": {"name": "In Progress", "type": "started"},
            "description": "",
        },
    }
    assert parse_linear_event(payload) is None


# ── Linear RA-888 instant create path ─────────────────────────────────────────

def test_parse_linear_issue_created_urgent():
    payload = {
        "type": "Issue",
        "action": "create",
        "data": {
            "id": "new-1",
            "title": "Prod is down",
            "priority": 1,  # Urgent
            "state": {"name": "Todo", "type": "unstarted"},
            "description": "repo:https://github.com/org/repo",
        },
    }
    event = parse_linear_event(payload)
    assert event is not None
    assert event["event"] == "issue_created"
    assert event["priority"] == 1
    assert event["repo_url"] == "https://github.com/org/repo"


def test_parse_linear_issue_created_high():
    payload = {
        "type": "Issue",
        "action": "create",
        "data": {
            "id": "new-2",
            "title": "Important",
            "priority": 2,  # High
            "state": {"type": "unstarted"},
            "description": "",
        },
    }
    event = parse_linear_event(payload)
    assert event is not None
    assert event["event"] == "issue_created"


def test_parse_linear_created_low_priority_skipped():
    payload = {
        "type": "Issue",
        "action": "create",
        "data": {
            "id": "new-3",
            "title": "Someday",
            "priority": 3,  # Normal — below the instant-trigger bar
            "state": {"type": "unstarted"},
        },
    }
    assert parse_linear_event(payload) is None


def test_parse_linear_created_started_state_skipped():
    payload = {
        "type": "Issue",
        "action": "create",
        "data": {
            "id": "new-4",
            "title": "Already moving",
            "priority": 1,
            "state": {"type": "started"},  # not unstarted → skip
        },
    }
    assert parse_linear_event(payload) is None


def test_parse_linear_unhandled_action_skipped():
    payload = {"type": "Issue", "action": "remove", "data": {"id": "x"}}
    assert parse_linear_event(payload) is None


def test_parse_linear_repo_from_label():
    # RA-6787 gap: repo URL supplied via a `repo:` label rather than description.
    payload = {
        "type": "Issue",
        "action": "update",
        "updatedFrom": {"stateId": "prev"},
        "data": {
            "id": "abc-123",
            "title": "Fix auth bug",
            "state": {"type": "started"},
            "labels": [{"name": "bug"}, {"name": "repo:https://github.com/org/repo"}],
            "description": "no repo line here",
        },
    }
    event = parse_linear_event(payload)
    assert event is not None
    assert event["repo_url"] == "https://github.com/org/repo"
    assert event["labels"] == ["bug", "repo:https://github.com/org/repo"]


# ── linear_issue_to_brief ─────────────────────────────────────────────────────

def test_brief_issue_started_includes_description():
    brief = linear_issue_to_brief({
        "title": "Fix auth bug",
        "description": "Users cannot log in",
        "priority": 3,
        "event": "issue_started",
    })
    assert "[NORMAL] Fix auth bug" in brief
    assert "Users cannot log in" in brief
    assert "moving to In Progress" in brief


def test_brief_issue_created_uses_instant_trigger_line():
    brief = linear_issue_to_brief({
        "title": "Prod is down",
        "description": "",
        "priority": 1,
        "event": "issue_created",
    })
    assert "[URGENT] Prod is down" in brief
    assert "RA-888 instant webhook" in brief


def test_brief_priority_labels_and_defaults():
    high = linear_issue_to_brief({"title": "H", "priority": 2, "event": "issue_started"})
    assert high.startswith("[HIGH] H")
    # Unknown/absent priority and event fall back to NORMAL + In-Progress trigger.
    fallback = linear_issue_to_brief({"title": "U"})
    assert fallback.startswith("[NORMAL] U")
    assert "moving to In Progress" in fallback
