from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.obsidian_analyst_relay import build_server


class UpstreamHandler(BaseHTTPRequestHandler):
    seen_path = ""
    seen_auth = ""
    seen_body = b""

    def log_message(self, *_args):
        return

    def do_PUT(self):  # noqa: N802
        type(self).seen_path = self.path
        type(self).seen_auth = self.headers.get("Authorization", "")
        length = int(self.headers.get("Content-Length", "0"))
        type(self).seen_body = self.rfile.read(length)
        self.send_response(204)
        self.end_headers()


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_relay_forwards_only_authenticated_analyst_writes():
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    _serve(upstream)
    upstream_url = f"http://127.0.0.1:{upstream.server_port}"

    relay = build_server("127.0.0.1", 0, upstream_url, "secret-token")
    _serve(relay)

    conn = http.client.HTTPConnection("127.0.0.1", relay.server_port, timeout=5)
    conn.request(
        "PUT",
        "/vault/Wiki/analyst/proof.md",
        body=b"# Proof\n",
        headers={"Authorization": "Bearer secret-token", "Content-Type": "text/markdown"},
    )
    resp = conn.getresponse()
    resp.read()

    assert resp.status == 204
    assert UpstreamHandler.seen_path == "/vault/Wiki/analyst/proof.md"
    assert UpstreamHandler.seen_auth == "Bearer secret-token"
    assert UpstreamHandler.seen_body == b"# Proof\n"

    conn.request(
        "PUT",
        "/vault/Wiki/private.md",
        body=b"# Private\n",
        headers={"Authorization": "Bearer secret-token", "Content-Type": "text/markdown"},
    )
    blocked = conn.getresponse()
    blocked.read()
    assert blocked.status == 403

    conn.close()
    relay.shutdown()
    upstream.shutdown()


def test_relay_writes_to_vault_filesystem_without_upstream(tmp_path):
    """With a vault configured, the relay writes the note directly to disk and
    needs no Obsidian app/upstream — the durable fix for production 'No Obsidian'."""
    vault = tmp_path / "vault"
    vault.mkdir()
    # upstream points nowhere reachable; filesystem path must be used instead.
    relay = build_server("127.0.0.1", 0, "http://127.0.0.1:1", "secret-token", str(vault))
    _serve(relay)

    conn = http.client.HTTPConnection("127.0.0.1", relay.server_port, timeout=5)
    conn.request(
        "PUT",
        "/vault/Wiki/analyst/proof.md",
        body=b"# Proof\n",
        headers={"Authorization": "Bearer secret-token", "Content-Type": "text/markdown"},
    )
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 204
    assert (vault / "Wiki" / "analyst" / "proof.md").read_bytes() == b"# Proof\n"

    conn.close()
    relay.shutdown()
