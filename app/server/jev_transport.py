"""The HTTP transport for live Jev calls: a wall-clock deadline, no redirects.

urlopen's timeout only bounds silence between bytes, so a server trickling a byte at a time could
hold a call indefinitely. Every call here runs on a worker thread and ends at JEV_DEADLINE_S of
wall-clock time: each socket the call opened is recorded the moment it exists (raw TCP before
TLS, and the TLS socket before its handshake) and shut down at the deadline, which ends the read
wherever it is (skill-router review rounds 5, 6 and 7).
"""
from __future__ import annotations

import functools
import http.client
import socket
import ssl
import threading
from typing import Callable
from urllib import request

JEV_DEADLINE_S = 3.0


def jev_ssl_context() -> ssl.SSLContext:
    """The TLS settings for Jev calls: the system trust store. Tests swap in a local CA."""
    return ssl.create_default_context()


class _TrackedHTTP(http.client.HTTPConnection):
    """Records its raw TCP socket at creation, before any header is read."""

    def __init__(self, *args, sockets: list, **kwargs):
        super().__init__(*args, **kwargs)
        self._sockets = sockets
        self._create_connection = self._record

    def _record(self, *args, **kwargs):
        sock = socket.create_connection(*args, **kwargs)
        self._sockets.append(sock)
        return sock


class _TrackedHTTPS(http.client.HTTPSConnection):
    """Records the raw socket, then the TLS socket BEFORE its handshake. wrap_socket detaches the
    raw socket it is given (its fd becomes -1), so the raw socket alone cannot be cut once TLS
    begins (review round 7)."""

    def __init__(self, *args, sockets: list, **kwargs):
        super().__init__(*args, **kwargs)
        self._sockets = sockets
        self._create_connection = self._record

    def _record(self, *args, **kwargs):
        sock = socket.create_connection(*args, **kwargs)
        self._sockets.append(sock)
        return sock

    def connect(self):
        http.client.HTTPConnection.connect(self)
        host = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=host, do_handshake_on_connect=False)
        self._sockets.append(self.sock)
        self.sock.do_handshake()


class _NoRedirect(request.HTTPRedirectHandler):
    """The request carries the Jev Bearer key, and urllib's default handler re-sends every header,
    Authorization included, to wherever a 3xx points, even another origin over plain HTTP (review
    round 7). Jev never redirects, so a 3xx is an error, not a hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def tracking_opener(sockets: list) -> request.OpenerDirector:
    """A urllib opener whose connections record every socket they open into `sockets`."""

    class HTTPHandler(request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(functools.partial(_TrackedHTTP, sockets=sockets), req)

    class HTTPSHandler(request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(functools.partial(_TrackedHTTPS, sockets=sockets), req,
                                context=jev_ssl_context())

    return request.build_opener(HTTPHandler, HTTPSHandler, _NoRedirect)


def _cut(sock) -> None:
    """End any read on this socket now. Closing the response would wait on the buffer lock the
    reading thread holds; shutting the socket down interrupts the read itself."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def within_deadline(run: Callable[[Callable], dict]) -> dict:
    """Run one Jev call, `run(opener)`, and return its result or raise TimeoutError at the deadline."""
    sockets: list = []
    tracked = tracking_opener(sockets)

    def opener(req, timeout=None):
        return tracked.open(req, timeout=JEV_DEADLINE_S)

    box: dict = {}

    def work():
        try:
            box["value"] = run(opener)
        except BaseException as exc:  # handed to the caller below
            box["error"] = exc

    worker = threading.Thread(target=work, name="skill-router-jev", daemon=True)
    worker.start()
    worker.join(JEV_DEADLINE_S)
    if worker.is_alive():
        for sock in sockets:
            _cut(sock)
        raise TimeoutError(f"Jev gave no complete answer within {JEV_DEADLINE_S}s")
    if "error" in box:
        raise box["error"]
    return box["value"]
