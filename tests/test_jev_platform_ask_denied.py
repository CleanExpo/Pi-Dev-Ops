"""Round 15 P0 controls for jev_platform.ask: an approved, committed file at a denied path is refused as denied.

Split from tests/test_jev_platform_ask.py (300-line convention); shares its fixtures.
"""
# ruff: noqa: F811  (test parameters named `repo` request the imported fixture)
from __future__ import annotations

import hashlib
import json

import pytest
from test_jev_platform_ask import GOOD, Recorder, git, good_answers, repo, run  # noqa: F401  (the shared `repo` fixture)

from jev_platform import ask

# Round 15 P0: a denied name must be refused BECAUSE it is denied. Each fixture below is committed, approved in the
# committed manifest with its true digest and holds benign text, so if its deny alternative were removed it would be
# sent. Each matches exactly one alternative of ask._DENY_NAMES (or, for IICRC, ask.sensitive on the path), so each
# alternative has a test that fails without it (tests/mutation/jev_platform_guard_mutants.py).
DENIED = ["config/.env.local", "certs/server.pem", "certs/server.key", "certs/client.p12", "certs/client.pfx",
          "vault/db.kdbx", "infra/main.tfstate", "keys/id_rsa", "keys/id_ed25519", "config/credentials.json",
          "config/app-secret.txt", ".npmrc", ".netrc", ".pypirc", ".git/HEAD", ".hermes/notes.md",
          ".ssh/known_hosts", ".aws/config", ".vercel/project.json", ".gcloud/settings.json", "IICRC/s500.md"]


def approve(repo, rel: str) -> None:
    """Commit `rel` with benign text and approve its digest in the committed manifest (.git/HEAD: git's own file)."""
    if not rel.startswith(".git/"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(GOOD)
    m = json.loads((repo / ask.MANIFEST).read_text())
    m["files"][rel] = hashlib.sha256((repo / rel).read_bytes()).hexdigest()
    (repo / ask.MANIFEST).write_text(json.dumps(m))
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", f"approve {rel}")


@pytest.mark.parametrize("path", DENIED)
def test_an_approved_committed_file_at_a_denied_path_is_refused_as_denied(repo, path):
    approve(repo, path)
    post = Recorder(good_answers)
    r = run(repo, [path], ["validates-tokens"], post)["results"][0]
    assert r["refused"] == "denied path" and post.calls == []


def test_the_same_approval_at_a_plain_path_is_sent(repo):
    """Positive control for the test above: the fixture itself is admissible, so only the name refuses it."""
    approve(repo, "src/plain.ts")
    post = Recorder(good_answers)
    r = run(repo, ["src/plain.ts"], ["validates-tokens"], post)["results"][0]
    assert "refused" not in r and len(post.calls) == 1
