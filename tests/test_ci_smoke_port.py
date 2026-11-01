"""CI smoke port isolation must be used by both original PR workflows."""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "ci_smoke_port.py"


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

    def test_export_appends_to_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "env"
            file.write_text("PRESERVED=yes\n")
            port = self.load_module().export_to_github_env(str(file))
            self.assertEqual(file.read_text(), f"PRESERVED=yes\nTAO_SMOKE_PORT={port}\n")

    def test_rejects_missing_runner_environment(self):
        with self.assertRaisesRegex(ValueError, "GITHUB_ENV"):
            self.load_module().export_to_github_env("")

    def test_both_smoke_workflows_use_isolated_port_and_live_server_guard(self):
        for name in ("ci.yml", "smoke_test.yml"):
            with self.subTest(workflow=name):
                content = (ROOT / ".github" / "workflows" / name).read_text()
                smoke = content[content.index("      - name: Allocate isolated smoke port"):]
                self.assertIn("run: python scripts/ci_smoke_port.py", smoke)
                self.assertIn('--port "$TAO_SMOKE_PORT"', smoke)
                self.assertIn("http://127.0.0.1:${TAO_SMOKE_PORT}/health", smoke)
                self.assertIn('--url "http://127.0.0.1:${TAO_SMOKE_PORT}"', smoke)
                self.assertIn('kill -0 "$SERVER_PID"', smoke)
                self.assertNotIn("127.0.0.1:7777", smoke)

    def test_real_cli_writes_single_port_to_runner_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "env"
            file.touch()
            run = subprocess.run([sys.executable, str(MODULE_PATH)],
                                 env={**os.environ, "GITHUB_ENV": str(file)},
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertRegex(file.read_text(), r"^TAO_SMOKE_PORT=\d+\n$")


if __name__ == "__main__":
    unittest.main()
