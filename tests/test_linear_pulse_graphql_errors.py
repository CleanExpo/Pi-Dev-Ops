"""Linear's refusal reason must reach the log.

Production (Railway, 28-29 Sept 2026) logged "portfolio-pulse comment FAILED to
post" 65 times with no `graphql error` line: Linear answered HTTP 200 with a
GraphQL `errors` array, and `_graphql()` discarded it. The heartbeat had been
failing silently since ~15 Sept with no stated cause.
"""

from __future__ import annotations

import io
import json
import logging
from unittest.mock import patch

from app.server import linear_pulse


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_graphql_errors_are_logged_not_swallowed(caplog, monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_key")
    body = {"data": None, "errors": [{"message": "Argument Validation Error"}]}
    with (
        patch("urllib.request.urlopen", return_value=_Resp(json.dumps(body).encode())),
        caplog.at_level(logging.WARNING, logger="pi-ceo.linear_pulse"),
    ):
        data = linear_pulse._graphql("mutation { x }")
    assert data == {}
    assert "Argument Validation Error" in caplog.text
