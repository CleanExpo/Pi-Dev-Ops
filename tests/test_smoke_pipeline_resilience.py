"""RA-7546 — Pipeline Smoke must not red on a Railway mid-session wipe."""
from __future__ import annotations

import json

from scripts.smoke_pipeline_resilience import (
    Probe,
    classify_backend,
    classify_session_list,
    find_session,
    parse_session_list,
    parse_uptime,
    should_respawn,
    wait_until_settled,
)


SID = "082af05e1ed7"


def test_502_is_bouncing_not_wiped():
    probe = Probe(http_status=502, sessions=None)
    assert classify_session_list(probe, SID) == "bouncing"
    assert should_respawn("bouncing") is True


def test_healthy_list_without_session_is_wiped():
    """In-memory store + no Railway volume: a restart lists nothing."""
    probe = Probe(http_status=200, sessions=[], uptime_s=12)
    assert classify_session_list(probe, SID) == "wiped"
    assert should_respawn("wiped") is True


def test_listed_session_is_found():
    probe = Probe(http_status=200, sessions=[{"id": SID, "status": "building"}])
    assert classify_session_list(probe, SID) == "found"
    assert find_session(probe.sessions or [], SID[:8])["status"] == "building"
    assert should_respawn("found") is False


def test_401_after_secret_rotate_is_auth_stale():
    probe = Probe(http_status=401, sessions=None)
    assert classify_session_list(probe, SID) == "auth_stale"
    assert classify_backend(probe) == "auth_stale"
    assert should_respawn("auth_stale") is True


def test_young_uptime_is_not_settled(monkeypatch):
    monkeypatch.setenv("SMOKE_SETTLE_UPTIME_S", "90")
    probe = Probe(http_status=200, sessions=[], uptime_s=12)
    assert classify_backend(probe) == "young"


def test_uptime_past_floor_is_settled(monkeypatch):
    monkeypatch.setenv("SMOKE_SETTLE_UPTIME_S", "90")
    probe = Probe(http_status=200, sessions=[], uptime_s=95)
    assert classify_backend(probe) == "settled"


def test_parse_helpers_accept_list_or_wrapped_payload():
    rows = parse_session_list(json.dumps({"sessions": [{"id": SID}]}))
    assert find_session(rows or [], SID)["id"] == SID
    assert parse_session_list("not-json") is None
    assert parse_uptime('{"status":"ok","uptime_s":42}') == 42
    assert parse_uptime('{"status":"ok"}') is None


def test_wait_settled_rides_out_502_then_young_uptime(monkeypatch):
    monkeypatch.setenv("SMOKE_SETTLE_UPTIME_S", "90")
    monkeypatch.setenv("SMOKE_SETTLE_POLL_S", "1")
    probes = [
        Probe(http_status=502),
        Probe(http_status=200, sessions=[], uptime_s=10),
        Probe(http_status=200, sessions=[], uptime_s=95),
    ]
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    ok = wait_until_settled(
        lambda: probes.pop(0),
        until=30.0,
        sleep_fn=sleep,
        now_fn=now,
        log=lambda _msg: None,
    )
    assert ok is True
    assert probes == []


def test_wait_settled_relogins_on_stale_cookie():
    probes = [
        Probe(http_status=401),
        Probe(http_status=200, sessions=[], uptime_s=120),
    ]
    logins = {"n": 0}

    def relogin() -> bool:
        logins["n"] += 1
        return True

    ok = wait_until_settled(
        lambda: probes.pop(0),
        until=10.0,
        relogin=relogin,
        sleep_fn=lambda _s: None,
        now_fn=lambda: 0.0,
        log=lambda _msg: None,
    )
    assert ok is True
    assert logins["n"] == 1


def test_gc_preserves_active_and_young_sessions(monkeypatch, tmp_path):
    """GC requires both a terminal state and age; blocked/stalled are terminal."""
    from unittest.mock import Mock
    from app.server import gc
    from app.server.session_model import BuildSession

    monkeypatch.setattr(gc.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(gc.config, "GC_MAX_AGE", 100)
    monkeypatch.setattr(gc.time, "time", lambda: 1000)
    deleted = Mock()
    monkeypatch.setattr(gc.persistence, "delete_session_file", deleted)
    cases = {"active": ("building", 500), "young": ("complete", 950)}
    cases.update({state: (state, 500) for state in (
        "complete", "failed", "killed", "interrupted", "blocked", "stalled")})
    sessions = {}
    for sid, (status, started_at) in cases.items():
        workspace = tmp_path / sid
        workspace.mkdir()
        sessions[sid] = BuildSession(id=sid, status=status, started_at=started_at,
                                     workspace=str(workspace))
    result = gc.collect_garbage(sessions)
    assert result == {"removed": 6, "skipped": 2, "errors": 0}
    assert set(sessions) == {"active", "young"}
    assert {call.args[0] for call in deleted.call_args_list} == set(cases) - set(sessions)
    assert {path.name for path in tmp_path.iterdir()} == {"active", "young"}
