"""Client coverage for mesh/report_ship.py (RA-7377).

The Stop-hook integration lives in tests/test_mesh_ship.py — this file pins
the reporter itself: remote URL parsing, collect() from a real checkout, and
publish() against a local sink.
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tests.mesh_helpers import load_module
from tests.test_mesh_ship import GIT_ENV, _commit, _git


@pytest.fixture
def reporter(monkeypatch, tmp_path):
    monkeypatch.delenv("PI_CEO_API_KEY", raising=False)
    monkeypatch.delenv("PI_CEO_API_URL", raising=False)
    monkeypatch.delenv("MESH_HOST", raising=False)
    # api_key()/api_url() fall back to ~/.hermes/.env on disk, so clearing the
    # process env is only half the isolation. On a machine that holds the estate
    # secret store the fallback handed the module a REAL key and inverted every
    # no-key assertion below — green on CI (which has no such file), red on the
    # developer box. Point HOME at an empty dir so the fallback finds nothing.
    # _git() in tests/test_mesh_ship.py passes an explicit env without HOME, so
    # the git helpers are unaffected by this.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return load_module("mesh_report_ship", "mesh/report_ship.py")


@pytest.fixture
def checkout(tmp_path: Path):
    """A clone on a mesh/* branch — same shape as tests/test_mesh_ship.py:mesh."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git("init", "--bare", "-q", cwd=origin)
    clone = tmp_path / "work"
    clone.mkdir()
    _git("init", "-q", "--initial-branch=fixture-base", cwd=clone)
    _git("remote", "add", "origin", str(origin), cwd=clone)
    (clone / ".autogit.json").write_text("{}\n", encoding="utf-8")
    _git("add", "-A", cwd=clone)
    _git("commit", "-q", "-m", "seed", cwd=clone)
    _git("checkout", "-q", "-b", "mesh/test-node/ra-7376-abc123", cwd=clone)
    return clone


def test_repo_from_remote_normalises_github_shapes(reporter):
    mod = reporter
    assert mod.repo_from_remote("git@github.com:CleanExpo/Pi-Dev-Ops.git") == (
        "CleanExpo/Pi-Dev-Ops"
    )
    assert mod.repo_from_remote("https://github.com/CleanExpo/Pi-Dev-Ops.git") == (
        "CleanExpo/Pi-Dev-Ops"
    )
    assert mod.repo_from_remote("/tmp/origin.git") == "tmp/origin"


def test_collect_reads_the_checkout(reporter, checkout, monkeypatch):
    _commit(checkout, "turn-output.txt")
    monkeypatch.chdir(checkout)
    monkeypatch.setenv("MESH_HOST", "test-node")
    payload = reporter.collect()
    assert payload["machine"] == "test-node"
    assert payload["branch"] == "mesh/test-node/ra-7376-abc123"
    assert payload["sha"] == _git("rev-parse", "HEAD", cwd=checkout)
    assert payload["subject"] == "add turn-output.txt"
    assert payload["files_changed"] == 1
    assert payload["repo"].endswith("origin")


def test_collect_collapses_hostname_when_mesh_host_unset(reporter, checkout, monkeypatch):
    monkeypatch.chdir(checkout)
    monkeypatch.delenv("MESH_HOST", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "Phills-Mac-mini.local")
    assert reporter.collect()["machine"] == "Phills-Mac-mini"


def test_publish_skips_without_a_key(reporter):
    ok, detail = reporter.publish({"machine": "h", "repo": "r"})
    assert ok is False
    assert "PI_CEO_API_KEY missing" in detail


def test_publish_skips_when_the_env_file_holds_no_key(reporter, tmp_path):
    """The disk fallback is the branch CI never reaches.

    CI has no ~/.hermes/.env, so _from_env_file() returns "" before it parses a
    line and the refusal is only ever proved for the env-var path. Plant a file
    that exists but carries no PI_CEO_API_KEY and prove publish still refuses.
    """
    hermes = tmp_path / "home" / ".hermes"
    hermes.mkdir(parents=True)
    (hermes / ".env").write_text("SOME_OTHER_KEY=value\n", encoding="utf-8")
    ok, detail = reporter.publish({"machine": "h", "repo": "r"})
    assert ok is False
    assert "PI_CEO_API_KEY missing" in detail


def test_api_key_survives_an_unreadable_env_file(reporter, tmp_path):
    """The third branch of _from_env_file: the file exists but cannot be read.

    The missing-file branch is covered by the fixture's empty HOME and the
    parse branch by the two tests above, but the OSError guard was never
    exercised — a reader that raised would have crashed the Stop hook instead
    of degrading to "no key". Planting a DIRECTORY at ~/.hermes/.env makes
    exists() true and read_text() raise IsADirectoryError (an OSError) for any
    user, which chmod 000 does not guarantee when the suite runs as root.
    """
    hermes = tmp_path / "home" / ".hermes"
    hermes.mkdir(parents=True)
    (hermes / ".env").mkdir()
    assert reporter.api_key() == ""
    ok, detail = reporter.publish({"machine": "h", "repo": "r"})
    assert ok is False
    assert "PI_CEO_API_KEY missing" in detail


def test_api_key_reads_the_env_file_fallback(reporter, tmp_path):
    """The other half of the same branch: a key on disk IS picked up.

    Without this, the fixture's HOME isolation could silently break the fallback
    and every no-key test would pass for the wrong reason.
    """
    hermes = tmp_path / "home" / ".hermes"
    hermes.mkdir(parents=True)
    (hermes / ".env").write_text("PI_CEO_API_KEY=disk-key-fixture\n", encoding="utf-8")
    assert reporter.api_key() == "disk-key-fixture"


def test_publish_posts_to_api_mesh_ship(reporter, monkeypatch):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            received.append({
                "path": self.path,
                "secret": self.headers.get("X-Pi-CEO-Secret"),
                "body": json.loads(self.rfile.read(length)),
            })
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("PI_CEO_API_URL", f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.setenv("PI_CEO_API_KEY", "feed-secret")
        ok, detail = reporter.publish({"machine": "h", "repo": "CleanExpo/Pi-Dev-Ops"})
    finally:
        server.shutdown()
    assert ok is True and detail == "200"
    assert received[0]["path"] == "/api/mesh/ship"
    assert received[0]["secret"] == "feed-secret"
    assert received[0]["body"]["repo"] == "CleanExpo/Pi-Dev-Ops"


def _autogit_that_commits_and_pushes(bindir: Path) -> Path:
    """Stub matching a successful autogit ship: commit dirty tree, then push."""
    bindir.mkdir(exist_ok=True)
    stub = bindir / "autogit"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "if [ -n \"$(git status --porcelain)\" ]; then\n"
        "  git add -A && git commit -q -m 'autogit ship'\n"
        "fi\n"
        "git push origin HEAD >/dev/null\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bindir


def _json_post_sink():
    """HTTP server that records JSON POST bodies. Caller must shutdown()."""
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return received, server


def test_wrapper_reports_when_autogit_already_pushed(checkout, tmp_path):
    """autogit shipped this turn; the wrapper push is up-to-date — still record it."""
    from tests.test_mesh_ship import _run
    bindir = _autogit_that_commits_and_pushes(tmp_path / "bin")
    (checkout / "uncommitted.txt").write_text("from autogit\n", encoding="utf-8")
    received, server = _json_post_sink()
    try:
        result = _run({"clone": checkout, "log": tmp_path / "ship.log"},
                      autogit_bin=bindir, extra_env={
                          "PI_CEO_API_URL": f"http://127.0.0.1:{server.server_address[1]}",
                          "PI_CEO_API_KEY": "k",
                          "MESH_HOST": "test-node",
                      })
        assert result.returncode == 0
        assert len(received) == 1
        assert received[0]["subject"] == "autogit ship"
    finally:
        server.shutdown()


# GIT_ENV is used by _git via the sibling module; keep the import load-bearing.
assert GIT_ENV["GIT_AUTHOR_NAME"]
