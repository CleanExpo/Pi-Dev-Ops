"""The Jev transport never outlives its deadline, never sends late, never carries the key through a
redirect, and a call that gets stuck never blocks the next one."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request

import pytest

from app.server import jev_transport

KEY = "Bearer LOCAL-DUMMY-KEY"


@pytest.fixture()
def recorder():
    """A local server that answers {"ok": true} and records every Authorization it receives."""
    seen = []

    class Record(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Record)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/", seen
    server.shutdown()


def _call(url):
    def run(opener):
        req = request.Request(url, data=b"{}", headers={"Authorization": KEY}, method="POST")
        with opener(req, timeout=15) as resp:
            return json.loads(resp.read(128_000))
    return jev_transport.within_deadline(run)


def _delayed_child(monkeypatch, seconds):
    """Stand in for an uncancellable DNS lookup: the child sleeps before it does anything."""
    path = jev_transport._CHILD[-1]
    code = (f"import time,runpy,sys; time.sleep({seconds}); sys.argv=[{path!r}]; "
            f"runpy.run_path({path!r}, run_name='__main__')")
    monkeypatch.setattr(jev_transport, "_CHILD", [sys.executable, "-I", "-S", "-c", code])


def test_the_transport_returns_a_real_answer(recorder):
    url, seen = recorder
    assert _call(url) == {"ok": True}
    assert seen == [KEY] and not jev_transport._CHILDREN


def test_nothing_is_sent_after_the_deadline(monkeypatch, recorder):
    """Review round 9 P1-JEV-POST-DEADLINE-EGRESS: a worker sent the brief and key after timing out."""
    url, seen = recorder
    monkeypatch.setattr(jev_transport, "JEV_DEADLINE_S", 0.3)
    _delayed_child(monkeypatch, 0.8)
    with pytest.raises(TimeoutError):
        _call(url)
    time.sleep(1.5)  # long past the moment the stalled child would have sent
    assert seen == [], f"the server received {seen} after the caller timed out"
    assert not jev_transport._CHILDREN


def test_a_permanently_stuck_call_never_blocks_the_next(monkeypatch, recorder):
    """Review round 9 P1-JEV-DNS-PERMANENT-STARVATION: a lookup that never returned held the slot."""
    url, _ = recorder
    monkeypatch.setattr(jev_transport, "JEV_DEADLINE_S", 0.3)
    real_child = jev_transport._CHILD
    _delayed_child(monkeypatch, 3600)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _call(url)
    assert time.monotonic() - started < 0.3 + 1.2
    assert not jev_transport._IN_FLIGHT.locked() and not jev_transport._CHILDREN
    monkeypatch.setattr(jev_transport, "_CHILD", real_child)
    assert _call(url) == {"ok": True}, "the next call must reach Jev, not fail with JevBusy"


def test_a_child_that_cannot_start_does_not_hold_the_slot(monkeypatch, recorder):
    def refuse(*args, **kwargs):
        raise OSError("no processes left")

    monkeypatch.setattr(jev_transport.subprocess, "Popen", refuse)
    with pytest.raises(OSError):
        _call(recorder[0])
    assert not jev_transport._IN_FLIGHT.locked()


def test_the_child_never_sees_the_key_in_its_environment(monkeypatch, recorder):
    """Review round 10 P1-JEV-CHILD-INHERITS-KEY-ENV: the child inherited TYPESAFE_API_KEY."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "LOCAL-DUMMY-KEY")
    code = ("import sys,os,json,base64; sys.stdin.buffer.read(); "
            "body=json.dumps({'env_has_key': any('LOCAL-DUMMY-KEY' in v for v in os.environ.values())}); "
            "print(json.dumps({'status': 200, 'body': base64.b64encode(body.encode()).decode()}))")
    monkeypatch.setattr(jev_transport, "_CHILD", [sys.executable, "-I", "-S", "-c", code])
    assert _call(recorder[0]) == {"env_has_key": False}


def test_a_malformed_key_never_comes_back_in_the_error():
    """Review round 10 P1-JEV-KEY-IN-RETURNED-EXCEPTION: the child's message quoted the header."""
    def run(opener):
        req = request.Request("http://127.0.0.1:9/", data=b"{}", method="POST",
                              headers={"Authorization": "Bearer LOCAL-DUMMY-KEY\nX"})
        return opener(req).read()

    with pytest.raises(Exception) as caught:
        jev_transport.within_deadline(run)
    assert "LOCAL-DUMMY-KEY" not in repr(caught.value) + str(caught.value)


def test_a_server_echoing_the_key_in_its_reason_never_reaches_the_error():
    class Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(429, self.headers.get("Authorization"))
            self.end_headers()
            self.wfile.write(self.headers.get("Authorization").encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(Exception) as caught:
            _call(f"http://127.0.0.1:{server.server_port}/")
    finally:
        server.shutdown()
    err = caught.value
    text = repr(err) + str(err) + str(getattr(err, "reason", "")) + repr(getattr(err, "read", lambda: b"")())
    assert getattr(err, "code", None) == 429 and "LOCAL-DUMMY-KEY" not in text


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
