"""The Jev transport never piles up workers and never carries the key through a redirect."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.server import jev_transport, skill_routing

BRIEF = "write a session handoff before I stop for the day"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")
    monkeypatch.setattr(skill_routing, "LEDGER", tmp_path / "ledger.sqlite")
    monkeypatch.setattr(skill_routing, "_CATALOGUE", None)
    monkeypatch.setattr(skill_routing, "_PINS", None)


def _workers():
    return sum(t.name == "skill-router-jev" for t in threading.enumerate())


def test_a_stalled_connect_never_leaves_more_than_one_worker(monkeypatch):
    """Review round 8 P1-JEV-CONNECT-STALL-LEAKS-WORKERS: three calls left three live workers."""
    release = threading.Event()

    def stalled_lookup(*args, **kwargs):
        release.wait(12)
        raise OSError("lookup abandoned")

    monkeypatch.setattr(jev_transport.socket, "getaddrinfo", stalled_lookup)
    monkeypatch.setattr("scripts.mission_control_jev_shadow.API_URL", "http://jev.invalid/")
    try:
        reasons = []
        for _ in range(3):
            started = time.monotonic()
            reasons.append(skill_routing._decide(BRIEF).reason)
            assert time.monotonic() - started < jev_transport.JEV_DEADLINE_S + 0.8
            assert _workers() <= 1, f"{_workers()} Jev workers alive"
        assert reasons[0] == "jev_error:TimeoutError"
        assert reasons[1:] == ["jev_error:JevBusy", "jev_error:JevBusy"]
    finally:
        release.set()
    deadline = time.monotonic() + 2
    while _workers() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _workers() == 0
    # Once the stuck worker has gone, Jev is usable again (the slot was released).
    assert not jev_transport._IN_FLIGHT.locked()


def test_a_worker_that_cannot_start_does_not_hold_the_slot(monkeypatch):
    def refuse(self):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    with pytest.raises(RuntimeError):
        jev_transport.within_deadline(lambda opener: {})
    assert not jev_transport._IN_FLIGHT.locked()


def test_the_bench_never_carries_the_key_through_a_redirect(monkeypatch):
    """Review round 8 P1-JEV-BENCH-REDIRECT-LEAKS-KEY: the bench's urlopen followed a 302 with the key."""
    from evals.skill_routing import run

    seen = []

    class Elsewhere(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *args):
            pass

    other = ThreadingHTTPServer(("127.0.0.1", 0), Elsewhere)
    threading.Thread(target=other.serve_forever, daemon=True).start()

    class Bouncer(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{other.server_port}/steal")
            self.end_headers()

        def log_message(self, *args):
            pass

    first = ThreadingHTTPServer(("127.0.0.1", 0), Bouncer)
    threading.Thread(target=first.serve_forever, daemon=True).start()
    monkeypatch.setattr(run, "JEV_URL", f"http://127.0.0.1:{first.server_port}/")
    try:
        with pytest.raises(Exception):
            run.jev_batch([(0, "hand off this session", [("session-handoff", "Hand off.")])], "LOCAL-DUMMY-KEY")
    finally:
        first.shutdown()
        other.shutdown()
    assert seen == [], f"the redirect target received {seen}"
