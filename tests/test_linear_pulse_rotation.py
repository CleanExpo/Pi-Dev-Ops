"""A full pulse issue must not stop the 15-min heartbeat.

Production (Railway, 2026-09-29T02:45Z), the first tick after #825 surfaced Linear's
refusal reason: RA-7391 held 2000 comments, Linear's hard per-issue cap, and every
pulse since ~15 Sept had been refused. The fix opens a fresh pulse issue when that
specific refusal arrives and posts there.

Mutation controls, each of which must make a test here fail:
  * make `is_comment_quota_error` always return False  -> rotation test fails
  * make it always return True                         -> the non-quota test fails
  * drop the retry post after rotating                 -> pulse_posted stays False
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from app.server import linear_pulse, linear_pulse_rotate

# Verbatim from the Railway deploy log, 2026-09-29T02:45:47Z.
QUOTA_ERRORS = [
    {
        "message": "quota exceeded",
        "path": ["commentCreate"],
        "locations": [{"line": 1, "column": 41}],
        "extensions": {
            "type": "internal error",
            "code": "QUOTA_EXCEEDED",
            "statusCode": 400,
            "userError": True,
            "userPresentableMessage": "An issue can have a maximum of 2000 comments. "
            "This quota is enforced to keep the workspace performant. If you would want "
            "to increase the limit, please send a request to support@linear.app.",
            "meta": {"quota": "max-comments-per-issue"},
        },
    }
]
RATE_LIMIT_ERRORS = [
    {"message": "rate limited", "extensions": {"code": "RATELIMITED", "userError": True}}
]


def test_quota_error_is_recognised() -> None:
    assert linear_pulse_rotate.is_comment_quota_error(QUOTA_ERRORS) is True


def test_other_errors_are_not_quota_errors() -> None:
    """Negative control — only the per-issue comment cap may trigger a rotation."""
    assert linear_pulse_rotate.is_comment_quota_error(RATE_LIMIT_ERRORS) is False
    assert linear_pulse_rotate.is_comment_quota_error([]) is False
    assert linear_pulse_rotate.is_comment_quota_error(None) is False


class _FakeLinear:
    """Stands in for `_graphql`: the old issue is full, anything new accepts comments."""

    def __init__(self, errors_for_full: list) -> None:
        self.errors_for_full = errors_for_full
        self.created: list[dict] = []
        self.comments: list[str] = []

    def __call__(self, query: str, variables: dict | None = None) -> dict:
        inp = (variables or {}).get("input") or {}
        if "issueCreate" in query:
            self.created.append(inp)
            return {"issueCreate": {"success": True, "issue": {"id": "new-pulse", "identifier": "RA-9"}}}
        if "commentCreate" in query:
            if inp.get("issueId") == "full-pulse":
                linear_pulse._last_errors = self.errors_for_full
                return {}
            self.comments.append(inp["issueId"])
            return {"commentCreate": {"success": True}}
        raise AssertionError(f"unexpected query: {query}")


def _tick(fake: _FakeLinear, monkeypatch) -> tuple[dict, dict]:
    monkeypatch.setenv("LINEAR_PULSE_TEAM_ID", "team-1")
    saved: dict = {}
    with (
        patch.object(linear_pulse, "_graphql", fake),
        patch.object(linear_pulse, "_active_sessions", return_value=[]),
        patch.object(linear_pulse, "_load_state", return_value={"pulse_issue_id": "full-pulse"}),
        patch.object(linear_pulse, "_save_state", lambda s: saved.update(s)),
        patch("app.server.digest.render_digest_text", return_value="body"),
    ):
        return linear_pulse.run_pulse(), saved


def test_full_pulse_issue_rotates_and_the_pulse_still_posts(monkeypatch) -> None:
    fake = _FakeLinear(QUOTA_ERRORS)
    summary, saved = _tick(fake, monkeypatch)

    assert len(fake.created) == 1, f"expected one new pulse issue, got {fake.created!r}"
    assert fake.created[0]["title"].startswith(linear_pulse._PULSE_ISSUE_TITLE + " — from ")
    assert "full-pulse" in fake.created[0]["description"], "new issue must link the full one"
    assert fake.comments == ["new-pulse"]
    assert saved["pulse_issue_id"] == "new-pulse"
    assert saved["retired_pulse_issue_ids"] == ["full-pulse"]
    assert summary["pulse_posted"] is True


def test_non_quota_refusal_does_not_rotate(monkeypatch, caplog) -> None:
    fake = _FakeLinear(RATE_LIMIT_ERRORS)
    with caplog.at_level(logging.INFO, logger="pi-ceo.linear_pulse"):
        summary, _ = _tick(fake, monkeypatch)

    assert fake.created == [], "a non-quota refusal must never open a new pulse issue"
    assert summary["pulse_posted"] is False
    assert any("portfolio-pulse comment FAILED to post" in r.getMessage() for r in caplog.records)


def test_lookup_picks_the_newest_pulse_issue(monkeypatch) -> None:
    """After a redeploy wipes local state, the search must land on the live issue, not RA-7391."""
    monkeypatch.setenv("LINEAR_PULSE_TEAM_ID", "team-1")
    nodes = [
        {"id": "full-pulse", "createdAt": "2026-08-31T12:25:02.838Z"},
        {"id": "new-pulse", "createdAt": "2026-09-29T03:00:00.000Z"},
    ]
    with (
        patch.object(linear_pulse, "_graphql", return_value={"issues": {"nodes": nodes}}),
        patch.object(linear_pulse, "_save_state", lambda s: None),
    ):
        assert linear_pulse._pulse_issue_id({}) == "new-pulse"
