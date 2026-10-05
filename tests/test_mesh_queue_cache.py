"""tests/test_mesh_queue_cache.py — the shared Linear read behind claim/self (RA-7910).

Pins: one read per TTL however many runners ask; a failed read backs off without
touching Linear; the queue is never served as empty when it could not be read;
and Linear's own error text (its rate-limit message) reaches the log.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server import mesh_lanes, mesh_queue_cache as cache  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    cache.reset()
    c = Clock()
    yield c
    cache.reset()


def _counting(result):
    calls = []

    def fake(graphql, strict=False):
        calls.append(strict)
        if isinstance(result, Exception):
            raise result
        return result
    return calls, fake


def test_many_claims_inside_the_ttl_read_linear_once(clock, monkeypatch):
    calls, fake = _counting(([{"identifier": "RA-1"}], {}))
    monkeypatch.setattr(mesh_lanes, "candidates", fake)
    for _ in range(5):
        assert cache.candidates(lambda q: {}, now=clock)[0][0]["identifier"] == "RA-1"
        clock.t += 10
    assert calls == [True]  # one strict read for five callers


def test_the_queue_is_read_again_after_the_ttl(clock, monkeypatch):
    calls, fake = _counting(([], {}))
    monkeypatch.setattr(mesh_lanes, "candidates", fake)
    cache.candidates(lambda q: {}, now=clock)
    clock.t += cache.TTL_S + 1
    cache.candidates(lambda q: {}, now=clock)
    assert len(calls) == 2


def test_a_failed_read_backs_off_without_touching_linear(clock, monkeypatch):
    calls, fake = _counting(mesh_lanes.IncompleteRead("rate limited"))
    monkeypatch.setattr(mesh_lanes, "candidates", fake)
    with pytest.raises(mesh_lanes.IncompleteRead):
        cache.candidates(lambda q: {}, now=clock)
    clock.t += 30
    with pytest.raises(mesh_lanes.IncompleteRead, match="backing off"):
        cache.candidates(lambda q: {}, now=clock)
    assert len(calls) == 1  # the second call never reached Linear


def test_reads_resume_after_the_backoff_and_a_good_read_clears_it(clock, monkeypatch):
    state = {"fail": True}

    def fake(graphql, strict=False):
        if state["fail"]:
            raise mesh_lanes.IncompleteRead("rate limited")
        return ([{"identifier": "RA-2"}], {})
    monkeypatch.setattr(mesh_lanes, "candidates", fake)
    with pytest.raises(mesh_lanes.IncompleteRead):
        cache.candidates(lambda q: {}, now=clock)
    state["fail"] = False
    clock.t += cache.BACKOFF_S + 1
    assert cache.candidates(lambda q: {}, now=clock)[0][0]["identifier"] == "RA-2"


def test_an_unreadable_queue_is_never_served_as_empty(clock, monkeypatch):
    monkeypatch.setattr(mesh_lanes, "candidates", _counting(mesh_lanes.IncompleteRead("x"))[1])
    with pytest.raises(mesh_lanes.IncompleteRead):
        cache.candidates(lambda q: {}, now=clock)


def _http_400(body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.linear.app/graphql", 400, "Bad Request", {},
                                  io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize("body", [b'{"errors":7}', b"null", b"[]", b'{"errors":null}', b'"x"', b"\xff\xfe"])
def test_a_malformed_linear_error_body_cannot_escape_the_route_handler(body, monkeypatch):
    """_linear_graphql calls linear_error_detail inside its except; a raise there skips the 503 path."""
    from app.server.routes import mesh as routes_mesh

    def refuse(req, timeout=None):
        raise urllib.error.HTTPError("https://api.linear.app/graphql", 400, "Bad Request", {}, io.BytesIO(body))
    monkeypatch.setattr(routes_mesh.config, "LINEAR_API_KEY", "lin_test_placeholder")
    monkeypatch.setattr(routes_mesh.urllib.request, "urlopen", refuse)
    assert routes_mesh._linear_graphql("query{viewer{id}}") == {}


def test_a_slow_failed_read_still_backs_off_from_when_it_failed(clock, monkeypatch):
    calls = []

    def slow_failure(graphql, strict=False):
        calls.append(clock.t)
        clock.t += cache.BACKOFF_S + 10  # 20 pages x 15 s timeouts can outlast the back-off
        raise mesh_lanes.IncompleteRead("rate limited")
    monkeypatch.setattr(mesh_lanes, "candidates", slow_failure)
    with pytest.raises(mesh_lanes.IncompleteRead):
        cache.candidates(lambda q: {}, now=clock)
    with pytest.raises(mesh_lanes.IncompleteRead, match="backing off"):
        cache.candidates(lambda q: {}, now=clock)
    assert len(calls) == 1  # the immediate retry did not reach Linear


def _blockable_route(monkeypatch, tmp_path):
    """claim/self over a fake Linear whose one ticket can be blocked after the shared read."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server.routes import mesh as routes_mesh
    labels = [{"name": "mesh:auto"}]
    node = {"id": "RA-T", "identifier": "RA-T", "title": "t", "description": "d", "priority": 1,
            "team": {"id": "team-1"}, "state": {"name": "Todo", "type": "unstarted"}, "labels": {"nodes": labels}}
    reads, mode = [], {"fresh_read_fails": False}

    def gql(q):
        reads.append(q[:12])
        if q.startswith("query{issue("):
            return {} if mode["fresh_read_fails"] else {"issue": node}  # {} is _linear_graphql's failure
        if q.startswith("query{team"):
            return {"team": {"states": {"nodes": [{"id": "st", "type": "started"}]}}}
        snapshot = {**node, "labels": {"nodes": list(labels)}}  # the list read is a copy, as Linear's JSON is
        return {"issueUpdate": {"success": True}} if q.startswith("mutation") else {"issues": {"nodes": [snapshot]}}
    monkeypatch.setattr(routes_mesh.config, "INTERNAL_WEBHOOK_SECRET", "s", raising=False)
    monkeypatch.setattr(mesh_lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(routes_mesh, "_linear_graphql", gql)
    monkeypatch.setattr(routes_mesh, "_sb", lambda method, path, payload=None, prefer="": (201, "") if method == "POST" else (200, "[]"))
    monkeypatch.setattr(routes_mesh, "_open_claim_ids", lambda: set())
    monkeypatch.setattr(routes_mesh, "_reap_sweep_best_effort", lambda: None)
    app = FastAPI()
    app.include_router(routes_mesh.router)
    claim = lambda: TestClient(app).post("/api/mesh/claim/self", json={"host": "n"}, headers={"X-Pi-CEO-Secret": "s"}).json()  # noqa: E731
    # The route's own cache module: a suite that re-imports app.server leaves this file's `cache` stale.
    route_cache = routes_mesh.mesh_queue_cache
    route_cache.reset()
    return claim, labels, reads, gql, mode, route_cache


def test_a_ticket_blocked_after_the_shared_read_is_not_claimed(monkeypatch, tmp_path):
    """Codex repro on 194e58f: the cached copy was claimed although Linear now blocks it."""
    claim, labels, reads, gql, _, route_cache = _blockable_route(monkeypatch, tmp_path)
    assert [n["identifier"] for n in route_cache.candidates(gql)[0]] == ["RA-T"]  # eligible when the shared read ran
    labels.append({"name": "pi-dev:blocked-reason:manual"})  # a human blocks it, inside the TTL
    assert claim()["claimed"] is None
    assert sum(r.startswith("query{issues") for r in reads) == 1  # still one shared queue read


def test_an_unblocked_ticket_is_still_claimed_after_its_fresh_read(monkeypatch, tmp_path):
    claim, _, reads, _, _, _ = _blockable_route(monkeypatch, tmp_path)
    assert claim()["claimed"]["linear_id"] == "RA-T"
    assert any(r.startswith("query{issue(") for r in reads)


def test_a_failed_fresh_read_is_unknown_not_an_empty_queue(monkeypatch, tmp_path):
    """Codex repro on ecff9d1: a failed re-read answered "queue empty" and evicted the ticket."""
    claim, _, _, gql, mode, route_cache = _blockable_route(monkeypatch, tmp_path)
    route_cache.candidates(gql)
    mode["fresh_read_fails"] = True
    from app.server.routes import mesh as routes_mesh
    with pytest.raises(Exception) as err:  # the route's 503
        routes_mesh.claim_self(routes_mesh.SelfClaimRequest(host="n"), x_pi_ceo_secret="s")
    assert getattr(err.value, "status_code", None) == 503
    assert [n["identifier"] for n in route_cache._state["value"][0]] == ["RA-T"]  # still cached, not evicted
    assert route_cache._state["failed_at"] is not None  # and the back-off has started


def test_a_failed_fresh_read_backs_off_like_a_failed_queue_read(clock, monkeypatch):
    """Codex repro on 025e126: three polls in one TTL each re-read a rate-limited Linear."""
    calls = []
    monkeypatch.setattr(mesh_lanes, "candidates", lambda g, strict=False: calls.append("queue") or ([{"identifier": "RA-T"}], {}))

    def gql(q):
        calls.append("fresh")
        return {}  # _linear_graphql's answer to any failure
    for _ in range(3):
        with pytest.raises(mesh_lanes.IncompleteRead):
            nodes, _ = cache.candidates(gql, now=clock)
            list(cache.rechecked(gql, nodes, now=clock))
        clock.t += 10
    assert calls == ["queue", "fresh"]  # one fresh read, then the back-off held
    clock.t += cache.BACKOFF_S
    assert cache.candidates(gql, now=clock)[0][0]["identifier"] == "RA-T"  # resumes after it


def test_a_walk_already_under_way_stops_when_a_peer_starts_the_back_off(clock, monkeypatch):
    """Codex repro on 470fa3e: a claim holding cached nodes re-read Linear during a peer's back-off."""
    reads = []
    monkeypatch.setattr(mesh_lanes, "explicit", lambda read, ids: read("q") and [])
    held = cache.rechecked(lambda q: reads.append(q) or {}, iter([{"identifier": "RA-T"}]), now=clock)
    cache._state.update(failed_at=clock.t)  # the peer's fresh read just failed
    with pytest.raises(mesh_lanes.IncompleteRead, match="backing off"):
        next(held)
    assert reads == []  # Linear was not touched


def test_a_null_issue_beside_a_graphql_error_is_unknown_not_refused(clock, monkeypatch):
    """Codex repro on 64fdd21: {"issue": null} from a field error evicted the ticket and said 'empty'."""
    monkeypatch.setattr(mesh_lanes, "explicit", lambda read, ids: read("q") and [])
    walk = cache.rechecked(lambda q: {"issue": None}, iter([{"identifier": "RA-T"}]), now=clock)
    with pytest.raises(mesh_lanes.IncompleteRead):
        next(walk)
    assert cache._state["failed_at"] == clock.t  # backs off; never a confirmed refusal


def test_every_fresh_candidate_is_offered_however_many_lose_a_race(monkeypatch):
    """Codex repro on 8a5f219: a cap of 5 re-reads hid RA-5 behind five 409s on RA-0..RA-4."""
    monkeypatch.setattr(mesh_lanes, "explicit", lambda read, ids: read("q") and [{"identifier": ids[0]}])
    offered = cache.rechecked(lambda q: {"issue": {"id": "x"}}, ({"identifier": f"RA-{i}"} for i in range(8)))
    assert [n["identifier"] for n in offered] == [f"RA-{i}" for i in range(8)]


def test_claim_self_reads_through_the_cache():
    src = (Path(__file__).resolve().parents[1] / "app" / "server" / "routes" / "mesh.py").read_text()
    assert "mesh_queue_cache.candidates(_linear_graphql)" in src
    assert "mesh_lanes.candidates(_linear_graphql, strict=True)" not in src
    assert "error_detail(e)" in src


def test_a_claimed_ticket_is_dropped_from_the_cached_queue(clock, monkeypatch):
    calls, fake = _counting(([{"identifier": "RA-1"}, {"identifier": "RA-2"}], {}))
    monkeypatch.setattr(mesh_lanes, "candidates", fake)
    assert [n["identifier"] for n in cache.candidates(lambda q: {}, now=clock)[0]] == ["RA-1", "RA-2"]
    cache.forget("RA-1")
    assert [n["identifier"] for n in cache.candidates(lambda q: {}, now=clock)[0]] == ["RA-2"]
    assert calls == [True]  # still one Linear read


def test_mark_in_progress_forgets_the_ticket():
    """Both claim paths (self-claim, dispatch) pass through _mark_issue_in_progress."""
    src = (Path(__file__).resolve().parents[1] / "app" / "server" / "routes" / "mesh.py").read_text()
    body = src.split("def _mark_issue_in_progress", 1)[1].split("\ndef ", 1)[0]
    assert "mesh_queue_cache.forget(" in body
