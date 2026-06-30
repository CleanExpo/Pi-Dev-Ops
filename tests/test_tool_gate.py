"""Tests for app/server/tool_gate.decide — the SDK-layer irreversible interceptor.

High precision is the contract: clearly-destructive commands are denied; ordinary
agent work (including non-destructive shell) is allowed so the loop can function.
"""
from __future__ import annotations

import pytest

from app.server.tool_gate import decide


# ---- allowed: non-Bash tools and benign shell --------------------------------

@pytest.mark.parametrize("tool,inp", [
    ("Read", {"file_path": "/x"}),
    ("Edit", {"file_path": "/x", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": "/x", "content": "y"}),
    ("Grep", {"pattern": "rm -rf"}),  # pattern arg, not a command — must not trip
    ("Bash", {"command": "ls -la && git status"}),
    ("Bash", {"command": "pytest -q && npm run build"}),
    ("Bash", {"command": "rm file.txt"}),          # plain delete, no -rf
    ("Bash", {"command": "git push origin feature"}),  # normal push
    ("Bash", {"command": "echo 'DROP the bass'"}),  # not SQL DDL
])
def test_allows_benign(tool, inp):
    d = decide(tool, inp)
    assert d.allow is True
    assert d.reversibility == "reversible"


def test_empty_and_none_input_allowed():
    assert decide("Bash", None).allow is True
    assert decide("Bash", {}).allow is True


# ---- denied: recognised irreversible operations ------------------------------

@pytest.mark.parametrize("cmd,label", [
    ("rm -rf /tmp/x", "rm-rf"),
    ("rm -fr build", "rm-rf"),
    ("rm -r -f node_modules", "rm-rf"),
    ("rm --recursive --force dist", "rm-rf"),
    ("git push --force origin main", "git-force-push"),
    ("git push origin main --force-with-lease", "git-force-push"),
    ("git push -f origin main", "git-force-push"),
    ("psql -c 'DROP TABLE users'", "sql-drop"),
    ("echo 'DROP DATABASE prod' | psql", "sql-drop"),
    ("psql -c 'TRUNCATE TABLE sessions'", "sql-truncate"),
    ("psql -c 'DELETE FROM users'", "sql-delete-no-where"),
    ("vercel deploy --prod", "vercel-prod"),
    ("vercel --prod", "vercel-prod"),
    ("supabase db push", "supabase-db-push"),
    ("npx prisma migrate deploy", "prisma-migrate"),
    ("npx prisma migrate reset", "prisma-migrate"),
    ("npm publish", "npm-publish"),
    ("gh release create v1.0", "gh-release"),
    ("terraform apply -auto-approve", "terraform"),
    ("terraform destroy", "terraform"),
    ("kubectl delete pod foo", "kubectl-delete"),
    ("mkfs.ext4 /dev/sda1", "mkfs"),
    ("dd if=/dev/zero of=/dev/sda", "dd-to-device"),
])
def test_denies_irreversible(cmd, label):
    d = decide("Bash", {"command": cmd})
    assert d.allow is False
    assert d.reversibility == "irreversible"
    assert d.label == label
    assert "founder" in d.reason.lower()


def test_delete_with_where_is_allowed():
    # A scoped DELETE is routine; only an unscoped DELETE FROM <table>; trips.
    d = decide("Bash", {"command": "psql -c 'DELETE FROM users WHERE id = 1'"})
    assert d.allow is True


def test_deny_reason_is_actionable():
    d = decide("Bash", {"command": "rm -rf /"})
    assert d.allow is False
    assert d.label == "rm-rf"
    assert "irreversible" in d.reason.lower()
