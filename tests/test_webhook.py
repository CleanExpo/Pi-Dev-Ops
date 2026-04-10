"""
test_webhook.py — Unit tests for GitHub and Linear webhook signature verification.
"""
import hashlib
import hmac
import json
import pytest

from app.server.webhook import (
    verify_github_signature,
    verify_linear_signature,
    parse_github_event,
    parse_linear_event,
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
        "data": {
            "id": "abc-123",
            "title": "Fix auth bug",
            "state": {"name": "In Progress"},
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
