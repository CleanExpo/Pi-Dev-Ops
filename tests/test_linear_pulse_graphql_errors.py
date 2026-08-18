"""A refused Linear mutation must say WHY, not merely that it failed.

Linear answers an APPLICATION error with HTTP 200, a top-level `errors` array and
`data: null` — an unknown or deleted issue id, a permission denial, an invalid input.
`_graphql` returned `.get("data", {}) or {}` and dropped `errors` on the floor, so the
caller saw an empty dict and logged "the 15-min heartbeat did not reach Linear this tick"
with no cause.

That ran every 15 minutes from 12:18 on 2026-08-18 without a single success and without one
diagnosable line. The `except (URLError, TimeoutError, JSONDecodeError)` branch never fired,
which is how we know the failure was at the GraphQL layer and not on the wire.

Sibling of test_linear_pulse_post_honesty.py: that one stopped the pulse CLAIMING success
when the post was refused (824fad72). This one makes the refusal explain itself. Honest but
uninformative is still undiagnosable.

Mutation control: restore `return (json.loads(resp.read()) or {}).get("data", {}) or {}` and
test_graphql_errors_are_logged must fail.
"""

from __future__ import annotations

import io
import json
import logging
from unittest.mock import patch

from app.server import linear_pulse


class _Resp(io.BytesIO):
    """Minimal stand-in for the urlopen context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen_returning(payload: dict):
    def _fake(_req, timeout=None):
        return _Resp(json.dumps(payload).encode())

    return _fake


def test_graphql_errors_are_logged(caplog) -> None:
    """The reason Linear refused must reach the log."""
    payload = {
        "data": None,
        "errors": [{"message": "Entity not found: Issue - Could not find referenced Issue."}],
    }

    with patch.object(linear_pulse, "_linear_key", return_value="lin_api_test"), \
         patch.object(linear_pulse.urllib.request, "urlopen", _urlopen_returning(payload)), \
         caplog.at_level(logging.ERROR, logger=linear_pulse.log.name):
        out = linear_pulse._graphql("mutation { x }")

    assert out == {}, "an errored response must not be treated as data"
    assert "Entity not found" in caplog.text, (
        "the GraphQL error was discarded — the caller can only report THAT it failed, "
        "never why, which is the defect this test exists to prevent"
    )


def test_a_successful_response_still_returns_data(caplog) -> None:
    """Positive control. Without this, returning {} unconditionally would pass the test above."""
    payload = {"data": {"commentCreate": {"success": True, "comment": {"id": "c1"}}}}

    with patch.object(linear_pulse, "_linear_key", return_value="lin_api_test"), \
         patch.object(linear_pulse.urllib.request, "urlopen", _urlopen_returning(payload)), \
         caplog.at_level(logging.ERROR, logger=linear_pulse.log.name):
        out = linear_pulse._graphql("mutation { x }")

    assert out == {"commentCreate": {"success": True, "comment": {"id": "c1"}}}
    assert "GraphQL errors" not in caplog.text, "a clean response must not log an error"


def test_post_comment_reports_failure_on_an_errored_response() -> None:
    """End to end: the caller still returns False, so honesty is preserved alongside the reason."""
    payload = {"data": None, "errors": [{"message": "Access denied"}]}

    with patch.object(linear_pulse, "_linear_key", return_value="lin_api_test"), \
         patch.object(linear_pulse.urllib.request, "urlopen", _urlopen_returning(payload)):
        posted = linear_pulse._post_comment("issue-123", "body")

    assert posted is False
