"""Every live Jev call ends at a wall-clock deadline, however slowly the server answers."""
import threading
import time

import pytest

from app.server import skill_routing

BRIEF = "write a session handoff before I stop for the day"


@pytest.fixture(autouse=True)
def no_live_jev(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(skill_routing, "LEDGER", tmp_path / "ledger.sqlite")
    monkeypatch.setattr(skill_routing, "_CATALOGUE", None)
    monkeypatch.setattr(skill_routing, "_PINS", None)


@pytest.fixture()
def trickle_server():
    """A local server that answers one byte every 0.1 s for 6 s: never silent for 3 s."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Trickle(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                for _ in range(60):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture()
def header_trickle_server():
    """A raw socket server that sends the status line one byte every 0.1 s: urlopen never returns."""
    import socket as sk

    srv = sk.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    stop = threading.Event()

    def serve():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            try:
                for ch in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"a" * 100:
                    if stop.is_set():
                        break
                    conn.sendall(bytes([ch]))
                    time.sleep(0.1)
            except OSError:
                pass
            finally:
                conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}/"
    stop.set()
    srv.close()


def _point_jev_at(monkeypatch, url):
    monkeypatch.setattr("scripts.mission_control_jev_shadow.API_URL", url)
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SKILL_ROUTER_REAL_DATA_EGRESS", "approved")


def _jev_workers_stop_within(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(t.name == "skill-router-jev" for t in threading.enumerate()):
        time.sleep(0.05)
    return not any(t.name == "skill-router-jev" for t in threading.enumerate())


def test_trickled_headers_are_cut_off_and_the_worker_stops(monkeypatch, header_trickle_server):
    """Review P1-JEV-HEADER-TRICKLE-LEAKS-WORKER: urlopen never returned, so nothing was closed."""
    import sqlite3

    _point_jev_at(monkeypatch, header_trickle_server)
    started = time.monotonic()
    d = skill_routing._decide(BRIEF)
    elapsed = time.monotonic() - started
    assert elapsed < skill_routing.JEV_DEADLINE_S + 0.8, f"Jev held the route for {elapsed:.2f}s"
    assert d.reason == "jev_error:TimeoutError"
    assert _jev_workers_stop_within(1.0), "the Jev worker is still reading after the deadline"
    with sqlite3.connect(skill_routing.LEDGER) as db:
        assert [r[0] for r in db.execute("SELECT status FROM calls")] == ["error"]


def test_a_trickling_jev_is_cut_off_at_the_wall_clock_deadline(monkeypatch, trickle_server):
    """Review P1-JEV-SOCKET-TIMEOUT-IS-NOT-WALL-CLOCK-DEADLINE: a byte every 0.1 s held the call 4.6 s."""
    _point_jev_at(monkeypatch, trickle_server)
    started = time.monotonic()
    d = skill_routing._decide(BRIEF)
    elapsed = time.monotonic() - started
    assert elapsed < skill_routing.JEV_DEADLINE_S + 0.8, f"Jev held the route for {elapsed:.2f}s"
    assert d.source == "lexical_fallback" and d.reason == "jev_error:TimeoutError"
    # The abandoned reader must actually stop, not trickle on in the background.
    assert _jev_workers_stop_within(1.0)


def test_a_trickling_jev_does_not_hold_the_shadow_lock(monkeypatch, trickle_server):
    _point_jev_at(monkeypatch, trickle_server)
    monkeypatch.setenv("SKILL_ROUTER", "shadow")
    skill_routing.skill_context(BRIEF, "feature")
    skill_routing.wait_for_shadow(timeout=skill_routing.JEV_DEADLINE_S + 2)
    assert not skill_routing._SHADOW_BUSY.locked()
