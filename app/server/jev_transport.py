"""The HTTP transport for live Jev calls: a wall-clock deadline, no redirects.

Each call's HTTP exchange runs in its own short-lived child process, killed at JEV_DEADLINE_S.
Killing the process ends whatever it was doing (a DNS lookup, a stalled connect, a TLS
handshake, a trickled header or body), and a dead process can send nothing after the deadline.
Review rounds 5 to 9 each found one more way a thread-and-socket version outlived its deadline
(body trickle, header trickle, TLS detach, connect stall, uncancellable DNS); a process has no
such corners. The request, Bearer key included, reaches the child on stdin, never argv or env:
the child gets only the certificate and proxy variables it needs (review round 10), and it
reports failures as exception class names and HTTP status codes, never as text that could
echo the key back (a malformed header value, or a server's reason phrase).

This file is also the child: run by path with `python -I -S`, it imports only the standard
library, so nothing from the app loads in the process that holds the key.
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import threading
import time
from typing import Callable
from urllib import error, request

JEV_DEADLINE_S = 3.0
_MAX_BODY = 1_000_000
_CHILD = [sys.executable, "-I", "-S", os.path.abspath(__file__)]
_CHILD_ENV = ("SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY",
              "http_proxy", "NO_PROXY", "no_proxy")

# One live Jev call at a time. The caller always frees the slot before it returns, because the
# child is dead by then; a stuck lookup can no longer hold it (review round 9).
_IN_FLIGHT = threading.Lock()
_CHILDREN: set = set()  # children not yet reaped; empty whenever no call is running


class JevBusy(RuntimeError):
    """Another Jev call is running right now; route without Jev."""


class _NoRedirect(request.HTTPRedirectHandler):
    """The request carries the Jev Bearer key, and urllib's default handler re-sends every header,
    Authorization included, to wherever a 3xx points, even another origin over plain HTTP (review
    round 7). Jev never redirects, so a 3xx is an error, not a hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def no_redirect_opener() -> request.OpenerDirector:
    """For callers without a deadline (the bench): the key still never follows a 3xx."""
    return request.build_opener(_NoRedirect)


def _spec(req: request.Request) -> bytes:
    return json.dumps({
        "url": req.full_url,
        "method": req.get_method(),
        "headers": dict(req.header_items()),
        "data": base64.b64encode(req.data or b"").decode("ascii"),
    }).encode("utf-8")


def _run_child(req: request.Request, deadline: float) -> dict:
    """Run one exchange in a child process; kill it at the deadline. Never starts one late."""
    if time.monotonic() >= deadline:
        raise TimeoutError("Jev deadline passed before the request could start")
    env = {name: os.environ[name] for name in _CHILD_ENV if name in os.environ}
    proc = subprocess.Popen(_CHILD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env)
    _CHILDREN.add(proc)
    try:
        out, _ = proc.communicate(_spec(req), timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Jev gave no complete answer within {JEV_DEADLINE_S}s") from None
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.communicate(timeout=1.0)  # reap it and close its pipes
            _CHILDREN.discard(proc)
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
    return json.loads(out or b'{"error": "NoReply"}')


def _exchange(req: request.Request, deadline: float) -> io.BytesIO:
    """What urlopen would return or raise, from the child's reply."""
    reply = _run_child(req, deadline)
    if "error" in reply:
        raise error.URLError(f"Jev child failed: {reply['error']}")
    if not 200 <= reply["status"] < 300:
        raise error.HTTPError(req.full_url, reply["status"], f"HTTP {reply['status']}", None,
                              io.BytesIO(b""))
    return io.BytesIO(base64.b64decode(reply["body"]))


def within_deadline(run: Callable[[Callable], dict]) -> dict:
    """Run one Jev call, `run(opener)`, and return its result, or raise TimeoutError at the
    deadline, or JevBusy at once while another call is running."""
    if not _IN_FLIGHT.acquire(blocking=False):
        raise JevBusy("another Jev call is running")
    deadline = time.monotonic() + JEV_DEADLINE_S
    try:
        return run(lambda req, timeout=None: _exchange(req, deadline))
    finally:
        _IN_FLIGHT.release()


def _child_main() -> int:
    """The child: read one request on stdin, make it without following redirects, print a reply."""
    spec = json.loads(sys.stdin.buffer.read())
    req = request.Request(spec["url"], data=base64.b64decode(spec["data"]) or None,
                          headers=spec["headers"], method=spec["method"])
    try:
        with no_redirect_opener().open(req, timeout=JEV_DEADLINE_S) as resp:
            reply = {"status": resp.status, "body": resp.read(_MAX_BODY)}
    except error.HTTPError as exc:
        reply = {"status": exc.code}
    except Exception as exc:  # class names only: a message can quote the Authorization header
        cause = getattr(exc, "reason", None)
        reply = {"error": type(exc).__name__ + (f":{type(cause).__name__}" if cause is not None else "")}
    if "body" in reply:
        reply["body"] = base64.b64encode(reply["body"]).decode("ascii")
    sys.stdout.write(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(_child_main())
