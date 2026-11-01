"""Smoke CI must identify the launched server, never an unrelated healthy listener."""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "ci_smoke_port.py"


@contextmanager
def serving_health(nonce: str | None, status: int = 200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            if nonce is not None:
                self.send_header("X-SDA-Smoke-Instance", nonce)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class SmokePortTests(unittest.TestCase):
    def load_module(self):
        spec = importlib.util.spec_from_file_location("ci_smoke_port", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_unused_port_can_be_bound(self):
        port = self.load_module().unused_loopback_port()
        with socket.socket() as server:
            server.bind(("127.0.0.1", port))

    def test_export_appends_port_and_nonce_to_runner_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "env"
            file.write_text("PRESERVED=yes\n")
            port, nonce = self.load_module().export_to_github_env(str(file))
            self.assertRegex(nonce, r"^[0-9a-f]{32}$")
            self.assertEqual(file.read_text(),
                             f"PRESERVED=yes\nTAO_SMOKE_PORT={port}\nTAO_SMOKE_NONCE={nonce}\n")

    def test_rejects_missing_runner_environment(self):
        with self.assertRaisesRegex(ValueError, "GITHUB_ENV"):
            self.load_module().export_to_github_env("")

    def test_foreign_healthy_listener_fails_closed(self):
        with serving_health(None) as port:
            self.assertFalse(self.load_module().matches_server(port, "expected-nonce"))

    def test_wrong_instance_nonce_fails_closed(self):
        with serving_health("different-instance") as port:
            self.assertFalse(self.load_module().matches_server(port, "expected-nonce"))

    def test_genuine_instance_health_passes_positive_control(self):
        with serving_health("expected-nonce") as port:
            self.assertTrue(self.load_module().matches_server(port, "expected-nonce"))

    def test_unhealthy_instance_never_passes_even_with_matching_nonce(self):
        with serving_health("expected-nonce", status=503) as port:
            self.assertFalse(self.load_module().matches_server(port, "expected-nonce"))

    def test_cli_checks_genuine_and_foreign_instances(self):
        with serving_health("expected-nonce") as port:
            command = [sys.executable, str(MODULE_PATH), "--check", str(port)]
            good = subprocess.run([*command, "expected-nonce"], capture_output=True)
            foreign = subprocess.run([*command, "foreign-nonce"], capture_output=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertNotEqual(foreign.returncode, 0)

    def test_real_cli_exports_port_and_nonce(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "env"
            file.touch()
            run = subprocess.run([sys.executable, str(MODULE_PATH)],
                                 env={**os.environ, "GITHUB_ENV": str(file)},
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertRegex(file.read_text(),
                             r"^TAO_SMOKE_PORT=\d+\nTAO_SMOKE_NONCE=[a-f0-9]{32}\n$")

    def test_shell_allocation_returns_port_and_nonce(self):
        run = subprocess.run([sys.executable, str(MODULE_PATH), "--emit-shell"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertRegex(run.stdout.strip(), r"^\d+ [a-f0-9]{32}$")

    def test_both_workflows_require_server_identity(self):
        for name in ("ci.yml", "smoke_test.yml"):
            with self.subTest(workflow=name):
                content = (ROOT / ".github" / "workflows" / name).read_text()
                smoke = content[content.index("      - name: Allocate isolated smoke port"):]
                self.assertIn("run: python scripts/ci_smoke_port.py", smoke)
                self.assertIn('--port "$TAO_SMOKE_PORT"', smoke)
                self.assertIn('--header "X-SDA-Smoke-Instance:$TAO_SMOKE_NONCE"', smoke)
                self.assertIn('ci_smoke_port.py --check "$TAO_SMOKE_PORT" "$TAO_SMOKE_NONCE"', smoke)
                self.assertIn('--url "http://127.0.0.1:${TAO_SMOKE_PORT}"', smoke)
                self.assertIn('kill -0 "$SERVER_PID"', smoke)
                self.assertNotIn("127.0.0.1:7777", smoke)

    def test_local_handoff_never_reuses_other_server(self):
        source = (ROOT / "scripts" / "handoff-loop.sh").read_text()
        smoke = source.split("_smoke_with_server() {", 1)[1].split('if [ "$PY_OK" = 1 ]', 1)[0]
        self.assertIn("ci_smoke_port.py --emit-shell", smoke)
        self.assertIn('ci_smoke_port.py --check "$port" "$nonce"', smoke)
        self.assertIn('--header "X-SDA-Smoke-Instance:$nonce"', smoke)
        self.assertIn('--url "http://127.0.0.1:$port"', smoke)
        self.assertNotIn("127.0.0.1:7777", smoke)


if __name__ == "__main__":
    unittest.main()
