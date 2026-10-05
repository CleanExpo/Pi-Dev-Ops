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


def test_linear_error_detail_surfaces_the_rate_limit_message():
    exc = _http_400({"errors": [{"message": "Rate limit exceeded. Only 2500 requests are allowed per 1 hour."}]})
    assert cache.linear_error_detail(exc).startswith("Rate limit exceeded")


def test_linear_error_detail_is_empty_for_non_http_errors_and_bad_bodies():
    assert cache.linear_error_detail(TimeoutError("slow")) == ""
    exc = urllib.error.HTTPError("u", 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))
    assert cache.linear_error_detail(exc) == ""


def test_claim_self_reads_through_the_cache():
    src = (Path(__file__).resolve().parents[1] / "app" / "server" / "routes" / "mesh.py").read_text()
    assert "mesh_queue_cache.candidates(_linear_graphql)" in src
    assert "mesh_lanes.candidates(_linear_graphql, strict=True)" not in src
    assert "linear_error_detail(e)" in src


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
