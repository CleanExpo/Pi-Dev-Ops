"""Production incident regression: Linear quota must not stall Mission Control."""

from __future__ import annotations

import asyncio
import io
import json
import random
import threading
import time
import urllib.error
from types import SimpleNamespace

import pytest

from app.server import autonomy
from app.server import autonomy_linear_rate
from app.server.routes import mission_control


@pytest.fixture(autouse=True)
def clear_cooldown(monkeypatch):
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", 0.0)
    monkeypatch.setattr(mission_control, "_queue_cache", None)
    monkeypatch.setattr(mission_control, "_pulse_cache", None)


def _http_error(status: int, payload: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.linear.app/graphql", status, "error", {}, io.BytesIO(payload),
    )


def test_http_429_stops_and_sanitizes_response(monkeypatch):
    secret = b"customer@example.com Bearer secret-private-token"
    def reject(*_args, **_kwargs):
        raise _http_error(429, secret)
    monkeypatch.setattr(autonomy.urllib.request, "urlopen", reject)

    with pytest.raises(autonomy.LinearRateLimitError) as caught:
        autonomy._gql("test-key", "query { viewer { id } }")
    assert "customer@example.com" not in str(caught.value)
    assert "secret-private-token" not in str(caught.value)
    assert autonomy.linear_rate_limited()


def test_graphql_400_quota_stops_without_response_body(monkeypatch):
    payload = json.dumps({"errors": [
        {"message": "other error"},
        {"message": "customer@example.com", "extensions": {"code": "RATELIMITED", "statusCode": 429}},
    ]}).encode()
    def reject(*_args, **_kwargs):
        raise _http_error(400, payload)
    monkeypatch.setattr(autonomy.urllib.request, "urlopen", reject)

    with pytest.raises(autonomy.LinearRateLimitError) as caught:
        autonomy._gql("test-key", "query { viewer { id } }")
    assert "customer@example.com" not in str(caught.value)
    assert autonomy.linear_rate_limited()


def test_long_graphql_400_quota_stops_portfolio_after_first_request(monkeypatch):
    payload = json.dumps({"errors": [
        {"message": "x" * 4200},
        {"message": "customer@example.com", "extensions": {"code": "RATELIMITED"}},
    ]}).encode()
    calls = []
    def reject(*_args, **_kwargs):
        calls.append(1)
        raise _http_error(400, payload)
    monkeypatch.setattr(autonomy.urllib.request, "urlopen", reject)
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [{
        "project_id": "a", "repo_url": "https://example.test/a", "team_id": "t", "name": "A",
    }])

    with pytest.raises(autonomy.LinearRateLimitError) as caught:
        autonomy.fetch_todo_issues("test-key")
    assert calls == [1]
    assert "customer@example.com" not in str(caught.value)
    assert autonomy.linear_rate_limited()


def test_oversized_http_error_stops_without_logging_body(monkeypatch):
    payload = b"customer@example.com" + b"x" * 65537
    def reject(*_args, **_kwargs):
        raise _http_error(400, payload)
    monkeypatch.setattr(autonomy.urllib.request, "urlopen", reject)
    with pytest.raises(autonomy.LinearRateLimitError) as caught:
        autonomy._gql("test-key", "query { viewer { id } }")
    assert "customer@example.com" not in str(caught.value)
    assert autonomy.linear_rate_limited()


def test_nonquota_vendor_errors_do_not_expose_response_bodies(monkeypatch):
    secret = b"customer@example.com Bearer secret-private-token"
    monkeypatch.setattr(autonomy.urllib.request, "urlopen", lambda *_a, **_kw: (
        (_ for _ in ()).throw(_http_error(500, secret))
    ))
    with pytest.raises(RuntimeError, match="Linear HTTP 500") as caught:
        autonomy._gql("test-key", "query { viewer { id } }")
    assert "customer@example.com" not in str(caught.value)
    assert "secret-private-token" not in str(caught.value)
    assert not autonomy.linear_rate_limited()


def test_quota_records_one_sanitized_poller_error(monkeypatch):
    events = []
    monkeypatch.setattr(autonomy, "_log_event", events.append)
    monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda _key: (
        (_ for _ in ()).throw(autonomy._mark_linear_rate_limited())
    ))
    config = SimpleNamespace(AUTONOMY_ENABLED=True, LINEAR_API_KEY="test-key")
    asyncio.run(autonomy._run_poller_iteration(config, None, True))
    assert len(events) == 1
    assert events[0]["action"] == "poll_error"
    assert "Linear rate limited" in events[0]["error"]


def test_quota_after_partial_result_drops_all_and_skips_remaining(monkeypatch):
    projects = [
        {"project_id": "a", "repo_url": "https://example.test/a", "team_id": "t", "name": "A"},
        {"project_id": "b", "repo_url": "https://example.test/b", "team_id": "t", "name": "B"},
    ]
    calls = []
    def gql(_key, _query, variables):
        calls.append((variables["projectId"], variables["autonomyLabel"]))
        if len(calls) == 2:
            raise autonomy.LinearRateLimitError("Linear rate limited; retry after cooldown")
        return {"project": {"issues": {"nodes": [{"id": "a1", "priority": 1,
            "state": {"name": "Ready for Pi-Dev", "type": "unstarted"},
            "labels": {"nodes": [{"name": "pi-dev:autonomous"}]}}]}}}
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: projects)
    monkeypatch.setattr(autonomy, "_gql", gql)

    with pytest.raises(autonomy.LinearRateLimitError):
        autonomy.fetch_todo_issues("test-key")
    assert len(calls) == 2


def _liveness(run_blocked):
    entered = threading.Event()
    release = threading.Event()
    ticker_ran_while_blocked = []

    def block():
        entered.set()
        release.wait(timeout=2)
        return []

    async def verify():
        timer = threading.Timer(0.35, release.set)
        timer.start()
        try:
            task = asyncio.create_task(run_blocked(block))
            while not entered.is_set():
                await asyncio.sleep(0.001)
            await asyncio.sleep(0)
            ticker_ran_while_blocked.append(not release.is_set())
            await asyncio.wait_for(task, timeout=2)
        finally:
            release.set()
            timer.join(timeout=2)

    asyncio.run(verify())
    assert ticker_ran_while_blocked == [True]


def test_queue_poll_does_not_block_event_loop(monkeypatch):
    config = SimpleNamespace(AUTONOMY_ENABLED=True, LINEAR_API_KEY="test-key")
    monkeypatch.setattr(autonomy, "_log_event", lambda *_args: None)

    async def run(block):
        monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda _key: block())
        await autonomy._run_poller_iteration(config, None, True)

    _liveness(run)


def test_startup_recovery_does_not_block_event_loop(monkeypatch):
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [{
        "project_id": "a", "repo_url": "https://example.test/a", "team_id": "t", "name": "A",
    }])

    async def run(block):
        monkeypatch.setattr(autonomy, "_gql", lambda *_args, **_kwargs: (
            block(), {"project": {"issues": {"nodes": []}}},
        )[1])
        await autonomy._orphan_recovery("test-key")

    _liveness(run)


def test_live_route_does_not_block_event_loop(monkeypatch):
    monkeypatch.setattr(mission_control, "_hourly_throughput_24h", lambda: [])
    monkeypatch.setattr(mission_control, "_active_sessions", lambda: [])
    monkeypatch.setattr(mission_control, "_recent_completions", lambda: [])
    monkeypatch.setattr(mission_control, "_pulse_status", lambda: {})
    monkeypatch.setattr(mission_control, "_claude_session_hud", lambda: {})
    monkeypatch.setattr(mission_control, "_idea_pipeline_snapshot", lambda *_args: {})
    monkeypatch.setattr(mission_control, "_nexus_one_status", lambda: {})
    async def observability():
        return {}
    monkeypatch.setattr(mission_control, "_observability_snapshot", observability)

    async def run(block):
        monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: block())
        await mission_control.mission_control_live()

    _liveness(run)


def test_live_cache_prevents_five_second_linear_hammer(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    calls = {"queue": 0, "pulse": 0}
    def queue():
        calls["queue"] += 1
        return {"urgent": 0, "high": 0, "next_issue_id": None, "next_issue_title": None}
    def pulse():
        calls["pulse"] += 1
        return {"last_at": None, "comments_today": 0, "pulse_issue_id": None}
    monkeypatch.setattr(mission_control, "_queue_snapshot", queue)
    monkeypatch.setattr(mission_control, "_pulse_status", pulse)

    for _ in range(1000):
        mission_control._cached_queue_snapshot()
        mission_control._cached_pulse_status()
    assert calls == {"queue": 1, "pulse": 1}


def test_cooldown_skips_all_live_linear_reads(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", time.monotonic() + 3600)
    monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: pytest.fail("queue queried"))
    monkeypatch.setattr(mission_control, "_pulse_status", lambda: pytest.fail("pulse queried"))
    assert mission_control._cached_queue_snapshot()["next_issue_id"] is None
    assert mission_control._cached_pulse_status()["pulse_issue_id"] is None


def test_failed_live_reads_are_not_cached_or_logged_with_vendor_body(monkeypatch, caplog):
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    calls = {"queue": 0, "pulse": 0}
    def queue():
        calls["queue"] += 1
        if calls["queue"] == 1:
            raise RuntimeError("vendor body customer@example.com")
        return {"next_issue_id": "RA-1"}
    def pulse():
        calls["pulse"] += 1
        if calls["pulse"] == 1:
            raise RuntimeError("vendor body customer@example.com")
        return {"pulse_issue_id": "PULSE-1"}
    monkeypatch.setattr(mission_control, "_queue_snapshot", queue)
    monkeypatch.setattr(mission_control, "_pulse_status", pulse)
    with caplog.at_level("DEBUG", logger="pi-ceo.mission_control"):
        assert mission_control._cached_queue_snapshot()["next_issue_id"] is None
        assert mission_control._cached_pulse_status()["pulse_issue_id"] is None
    assert "customer@example.com" not in caplog.text
    assert mission_control._cached_queue_snapshot()["next_issue_id"] == "RA-1"
    assert mission_control._cached_pulse_status()["pulse_issue_id"] == "PULSE-1"
    assert calls == {"queue": 2, "pulse": 2}


def test_failed_portfolio_scan_is_not_cached_as_empty_queue(monkeypatch, caplog):
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [{
        "project_id": "a", "repo_url": "https://example.test/a", "team_id": "t", "name": "A",
    }])
    calls = []
    issue = {"id": "a1", "identifier": "RA-1", "title": "Recovered", "priority": 1,
             "state": {"name": "Ready for Pi-Dev", "type": "unstarted"},
             "labels": {"nodes": [{"name": "pi-dev:autonomous"}]}}
    def gql(_key, _query, _variables):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Linear HTTP 500 customer@example.com")
        return {"project": {"issues": {"nodes": [issue]}}}
    monkeypatch.setattr(autonomy, "_gql", gql)

    with caplog.at_level("DEBUG", logger="pi-ceo.mission_control"):
        assert mission_control._cached_queue_snapshot()["next_issue_id"] is None
    assert mission_control._queue_cache is None
    assert "customer@example.com" not in caplog.text
    assert mission_control._cached_queue_snapshot()["next_issue_id"] == "RA-1"
    assert len(calls) == 3
    assert mission_control._cached_queue_snapshot()["next_issue_id"] == "RA-1"
    assert len(calls) == 3
