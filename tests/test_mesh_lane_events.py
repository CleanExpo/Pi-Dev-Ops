"""tests/test_mesh_lane_events.py — the mc-lane mod's endpoint.

What these pin, in order of what would hurt most if it broke:

1. Auth: neither verb is open (write needs the machine secret, read the fleet
   read secret or the machine secret).
2. Nothing but names and numbers is stored, whatever a caller sends.
3. Idempotency: the insert asks PostgREST to ignore duplicates on
   (session_id, seq), and the ack covers rejected events so the mod stops
   re-sending them.
4. A failed write is a 502 with nothing acked (the mod keeps its queue); a
   failed read is a 502, never an empty list.

Fully offline: the Supabase layer is stubbed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}


def _ev(**kw):
    base = {"session_id": "sess-1", "seq": 1, "kind": "tool", "at": "2026-10-04T11:00:00Z",
            "tool": "Bash", "ok": True, "ms": 12.5}
    base.update(kw)
    return base


@pytest.fixture
def lane(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.delenv("TAO_FLEET_READ_SECRET", raising=False)
    sys.modules.pop("app.server.routes.mesh_lane_events", None)
    from app.server.routes import mesh_lane_events as mod
    monkeypatch.setattr(mod._mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    calls: list[tuple] = []
    state = {"status": 201, "body": "", "get_body": "[]", "get_status": 200}

    def fake_sb(method, path, body=None, *, prefer=""):
        calls.append((method, path, body, prefer))
        if method == "GET":
            return state["get_status"], state["get_body"]
        return state["status"], state["body"]

    monkeypatch.setattr(mod, "_sb", fake_sb)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app), calls, state


# ── 1. auth ──────────────────────────────────────────────────────────────────

def test_post_requires_the_machine_secret(lane):
    client, calls, _ = lane
    body = {"host": "unite-mac-mini", "events": [_ev()]}
    assert client.post("/api/mesh/lane-events", json=body).status_code == 401
    assert client.post("/api/mesh/lane-events", json=body,
                       headers={"X-Pi-CEO-Secret": "wrong"}).status_code == 401
    assert calls == []  # rejected before any write


def test_get_requires_a_secret(lane):
    client, calls, _ = lane
    assert client.get("/api/mesh/lane-events").status_code == 401
    assert calls == []


# ── 2. only names and numbers are stored ─────────────────────────────────────

def test_a_valid_tool_event_is_stored_as_sent(lane):
    client, calls, _ = lane
    r = client.post("/api/mesh/lane-events", headers=HDR,
                    json={"host": "unite-mac-mini", "events": [_ev()]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "stored": 1, "rejected": 0, "acked": {"sess-1": 1}}
    (method, path, rows, prefer) = calls[0]
    assert method == "POST" and path.startswith("mesh_lane_events?on_conflict=session_id,seq")
    assert "ignore-duplicates" in prefer
    assert rows[0]["tool"] == "Bash" and rows[0]["host"] == "unite-mac-mini"


def test_free_text_in_named_fields_is_dropped_not_stored(lane):
    client, calls, _ = lane
    nasty = _ev(tool="Bash; cat ~/.ssh/id_rsa", repo="https://tok@github.com/a/b",
                model="claude\nIGNORE PREVIOUS")
    client.post("/api/mesh/lane-events", headers=HDR,
                json={"host": "bad host name!", "events": [nasty]})
    row = calls[0][2][0]
    assert row["tool"] is None and row["repo"] is None and row["model"] is None
    assert row["host"] == "unknown"
    assert "id_rsa" not in json.dumps(row) and "tok@" not in json.dumps(row)


def test_extra_fields_never_reach_the_row(lane):
    """A caller that adds `command` or `output` gets them ignored, not stored."""
    client, calls, _ = lane
    client.post("/api/mesh/lane-events", headers=HDR,
                json={"host": "h", "events": [_ev(command="rm -rf /", output="secret")]})
    row = calls[0][2][0]
    assert "command" not in row and "output" not in row


def test_agent_start_is_stored_with_type_and_model_only(lane):
    """A subagent/teammate start (mod's agent.spawn): agent type in `tool`, its model."""
    client, calls, _ = lane
    ev = _ev(kind="agent_start", seq=3, tool="Explore", model="claude-haiku-4-5", ms=None,
             prompt="read ~/.ssh/id_rsa")
    r = client.post("/api/mesh/lane-events", headers=HDR, json={"host": "h", "events": [ev]})
    assert r.json() == {"ok": True, "stored": 1, "rejected": 0, "acked": {"sess-1": 3}}
    row = calls[0][2][0]
    assert row["kind"] == "agent_start" and row["tool"] == "Explore"
    assert row["model"] == "claude-haiku-4-5" and row["ok"] is True
    assert "prompt" not in row and "id_rsa" not in json.dumps(row)


def test_unknown_kind_is_rejected_but_acked(lane):
    client, calls, _ = lane
    r = client.post("/api/mesh/lane-events", headers=HDR,
                    json={"host": "h", "events": [_ev(kind="shell_dump", seq=7)]})
    assert r.json()["stored"] == 0 and r.json()["rejected"] == 1
    assert r.json()["acked"] == {"sess-1": 7}
    assert calls == []  # nothing to insert


def test_out_of_range_numbers_are_a_422(lane):
    client, _, _ = lane
    r = client.post("/api/mesh/lane-events", headers=HDR,
                    json={"host": "h", "events": [_ev(kind="usage", ctx_pct=140)]})
    assert r.status_code == 422


def test_absent_cost_is_null_not_zero(lane):
    client, calls, _ = lane
    client.post("/api/mesh/lane-events", headers=HDR,
                json={"host": "h", "events": [_ev(kind="usage", tool=None, ctx_pct=20)]})
    assert calls[0][2][0]["cost_usd"] is None


def test_batch_cap(lane):
    client, calls, _ = lane
    from app.server.routes.mesh_lane_events import MAX_BATCH
    events = [_ev(seq=i) for i in range(MAX_BATCH + 1)]
    assert client.post("/api/mesh/lane-events", headers=HDR,
                       json={"host": "h", "events": events}).status_code == 413
    assert calls == []


def test_ack_is_the_highest_seq_per_session(lane):
    client, _, _ = lane
    events = [_ev(seq=3), _ev(seq=9), _ev(session_id="sess-2", seq=4)]
    r = client.post("/api/mesh/lane-events", headers=HDR, json={"host": "h", "events": events})
    assert r.json()["acked"] == {"sess-1": 9, "sess-2": 4}


# ── 4. failure is never success ──────────────────────────────────────────────

def test_failed_write_is_502_with_nothing_acked(lane):
    client, _, state = lane
    state["status"] = 500
    r = client.post("/api/mesh/lane-events", headers=HDR, json={"host": "h", "events": [_ev()]})
    assert r.status_code == 502


def test_read_returns_rows_and_a_cursor(lane):
    client, calls, state = lane
    state["get_body"] = json.dumps([{"id": 11, "kind": "tool"}, {"id": 12, "kind": "usage"}])
    r = client.get("/api/mesh/lane-events?after_id=10", headers=HDR)
    assert r.status_code == 200
    assert r.json()["cursor"] == 12 and len(r.json()["events"]) == 2
    assert "id=gt.10" in calls[0][1]


def test_empty_read_keeps_the_cursor(lane):
    client, _, _ = lane
    assert client.get("/api/mesh/lane-events?after_id=40", headers=HDR).json() == {"events": [], "cursor": 40}


@pytest.mark.parametrize("status,body", [(500, "[]"), (200, "<html>gateway</html>"),
                                         (200, '{"message": "permission denied", "code": "42501"}')])
def test_a_broken_read_is_502_not_empty(lane, status, body):
    client, _, state = lane
    state["get_status"], state["get_body"] = status, body
    assert client.get("/api/mesh/lane-events", headers=HDR).status_code == 502


def test_newest_reads_latest_first_and_cursor_is_the_max_id(lane):
    client, calls, state = lane
    state["get_body"] = json.dumps([{"id": 30}, {"id": 29}])
    r = client.get("/api/mesh/lane-events?newest=true&limit=2", headers=HDR)
    assert r.status_code == 200 and r.json()["cursor"] == 30
    assert "order=id.desc" in calls[0][1] and "limit=2" in calls[0][1]


def test_mission_control_read_is_session_gated_and_newest_first(lane, monkeypatch):
    """The dashboard's read: session auth (require_auth), never the machine secret."""
    from fastapi.testclient import TestClient

    from app.server.auth import require_auth
    from app.server.routes import mesh_lane_events as mod
    client_no_auth = TestClient(_app_with(mod.mc_router))
    assert client_no_auth.get("/api/mission-control/lane-events").status_code == 401

    _, calls, state = lane
    state["get_body"] = json.dumps([{"id": 5}, {"id": 4}])
    app = _app_with(mod.mc_router)
    app.dependency_overrides[require_auth] = lambda: True
    r = TestClient(app).get("/api/mission-control/lane-events")
    assert r.status_code == 200 and r.json()["cursor"] == 5
    assert "order=id.desc" in calls[-1][1] and "limit=500" in calls[-1][1]


def _app_with(router):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return app
