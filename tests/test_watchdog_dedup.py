"""tests/test_watchdog_dedup.py — RA-1939 regression.

Locks the contract: `_has_open_linear_issue_with_prefix` returns True when
Linear has an OPEN issue matching the prefix, False otherwise, and never
raises (fail-open on any error).

Caught after 2026-05-03/04 produced 6 duplicate auto-noise tickets
(RA-1924/1925/1935/1936/1937 + RA-1880's parent) because the in-process
module-level cooldown reset to 0.0 on every gateway restart.
"""
from __future__ import annotations

import json
import logging
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture
def _set_linear_key(monkeypatch):
    import app.server.config as config
    monkeypatch.setattr(config, "LINEAR_API_KEY", "lin_api_test_key", raising=False)
    yield
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)


def _mock_linear_response(nodes: list[dict]):
    """Build a urlopen-style mock returning the given nodes."""
    body = json.dumps({"data": {"issues": {"nodes": nodes}}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda self: self
    mock_resp.__exit__ = lambda *a: False
    return mock_resp


def test_returns_false_when_no_linear_key(monkeypatch, caplog):
    """No API key → no query → fail-open False."""
    import app.server.config as config
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)
    log = logging.getLogger("pi-ceo")
    assert cw._has_open_linear_issue_with_prefix("[WATCHDOG]", log) is False


def test_returns_true_when_open_issue_matches(_set_linear_key, caplog):
    """Open issue with matching prefix → True (caller skips ticket creation)."""
    log = logging.getLogger("pi-ceo")
    nodes = [
        {"identifier": "RA-1880", "title": "[WATCHDOG] Board-meeting silence...",
         "state": {"name": "Pi-Dev: Blocked", "type": "started"}}
    ]
    with patch("urllib.request.urlopen", return_value=_mock_linear_response(nodes)):
        with caplog.at_level(logging.INFO, logger="pi-ceo"):
            result = cw._has_open_linear_issue_with_prefix(
                "[WATCHDOG] Board-meeting silence", log,
            )
    assert result is True
    assert any("RA-1880" in rec.message for rec in caplog.records)


def test_returns_false_when_no_open_issue(_set_linear_key):
    """Empty nodes list → False (caller proceeds with creation)."""
    log = logging.getLogger("pi-ceo")
    with patch("urllib.request.urlopen", return_value=_mock_linear_response([])):
        result = cw._has_open_linear_issue_with_prefix("[WATCHDOG]", log)
    assert result is False


def test_fails_open_on_network_error(_set_linear_key, caplog):
    """Network exception → returns False (fail-open)."""
    log = logging.getLogger("pi-ceo")
    with patch("urllib.request.urlopen", side_effect=ConnectionError("network down")):
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            result = cw._has_open_linear_issue_with_prefix("[WATCHDOG]", log)
    assert result is False
    assert any("Linear query failed" in rec.message for rec in caplog.records)


def test_fails_open_on_malformed_response(_set_linear_key):
    """Garbage response → False (fail-open) without raising."""
    log = logging.getLogger("pi-ceo")
    bad_resp = MagicMock()
    bad_resp.read.return_value = b"not json"
    bad_resp.__enter__ = lambda self: self
    bad_resp.__exit__ = lambda *a: False
    with patch("urllib.request.urlopen", return_value=bad_resp):
        result = cw._has_open_linear_issue_with_prefix("[WATCHDOG]", log)
    assert result is False


def test_query_includes_correct_filter_shape(_set_linear_key):
    """Sanity-check the GraphQL query targets startsWith + open-state filter."""
    log = logging.getLogger("pi-ceo")
    captured = {}
    def _capture_urlopen(req, timeout=None):
        captured["data"] = req.data
        return _mock_linear_response([])
    with patch("urllib.request.urlopen", side_effect=_capture_urlopen):
        cw._has_open_linear_issue_with_prefix("[WATCHDOG] Board-meeting silence", log)
    body = json.loads(captured["data"])
    assert "startsWith" in body["query"]
    assert body["variables"]["prefix"] == "[WATCHDOG] Board-meeting silence"
    assert "backlog" in body["query"]
    assert "started" in body["query"]
    # Pi - Dev -Ops project ID locked in the query
    assert "f45212be-3259-4bfb-89b1-54c122c939a7" in body["query"]
