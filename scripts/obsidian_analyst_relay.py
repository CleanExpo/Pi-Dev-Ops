#!/usr/bin/env python3
"""Narrow Obsidian relay for production analyst-note writes.

This is intentionally smaller than exposing the full Obsidian Local REST API
through a public tunnel. It accepts only authenticated PUT requests under
`/vault/Wiki/analyst/` and forwards them to the local Obsidian REST listener.
"""

from __future__ import annotations

import argparse
import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 27125
DEFAULT_UPSTREAM = "http://127.0.0.1:27123"
ALLOWED_PREFIX = "/vault/Wiki/analyst/"


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "ObsidianAnalystRelay/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802
        token = self.server.obsidian_token  # type: ignore[attr-defined]
        auth = self.headers.get("Authorization", "")
        if not token or auth != f"Bearer {token}":
            self.send_error(401)
            return

        parsed_path = urlparse(self.path).path
        if not parsed_path.startswith(ALLOWED_PREFIX):
            self.send_error(403)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        body = self.rfile.read(length)

        upstream = urlparse(self.server.upstream_url)  # type: ignore[attr-defined]
        conn = http.client.HTTPConnection(upstream.hostname, upstream.port or 80, timeout=15)
        try:
            target = self.path
            conn.request(
                "PUT",
                target,
                body=body,
                headers={
                    "Authorization": auth,
                    "Content-Type": self.headers.get("Content-Type", "text/markdown"),
                    "Content-Length": str(len(body)),
                },
            )
            resp = conn.getresponse()
            data = resp.read()
        except OSError as exc:
            self.send_error(502, f"Upstream failed: {exc}")
            return
        finally:
            conn.close()

        self.send_response(resp.status)
        for key, value in resp.getheaders():
            if key.lower() not in {"connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)


def build_server(host: str, port: int, upstream_url: str, token: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), RelayHandler)
    server.upstream_url = upstream_url.rstrip("/")  # type: ignore[attr-defined]
    server.obsidian_token = token  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the narrow Obsidian analyst-note relay.")
    parser.add_argument("--host", default=os.environ.get("OBSIDIAN_RELAY_HOST", DEFAULT_LISTEN_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OBSIDIAN_RELAY_PORT", DEFAULT_LISTEN_PORT)))
    parser.add_argument("--upstream", default=os.environ.get("OBSIDIAN_RELAY_UPSTREAM", DEFAULT_UPSTREAM))
    args = parser.parse_args()

    token = os.environ.get("OBSIDIAN_TOKEN", "")
    if not token:
        raise SystemExit("OBSIDIAN_TOKEN is required")

    server = build_server(args.host, args.port, args.upstream, token)
    print(
        f"obsidian analyst relay listening on http://{args.host}:{args.port} "
        f"-> {args.upstream} ({ALLOWED_PREFIX} only)",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
