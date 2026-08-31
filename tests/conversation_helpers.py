"""tests/conversation_helpers.py — shared setup for the conversation-lane tests.

Not a test module. `test_conversations_api.py` (route contract) and
`test_conversations_redaction.py` (the second redaction pass and its fail-closed
behaviour) both need the same offline harness, and the two of them together
exceed the repo's 300-line file ceiling, so the harness lives here rather than
being duplicated or wedged into `conftest.py` — conftest sets env vars that must
land before any app import, and this pulls app modules in.

Everything here is offline by construction: `FakeStore` replaces the Supabase
layer, so no test using it can reach a network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}

# Syntactically live-shaped, not real credentials: the prefix is real, the body
# is fixed filler. That is what makes them positive controls — the patterns MUST
# match, so a redactor that silently stopped running lets them through
# unchanged. `tests/` is a reviewed-fixture exclusion in
# `scripts/secrets_check.py`, which is why these do not trip the secret gate.
FAKE_ANTHROPIC_KEY = "sk-ant-api03-" + "A1b2C3d4E5" * 5
FAKE_OAUTH_TOKEN = "sk-ant-oat01-" + "Z9y8X7w6V5" * 4


class FakeStore:
    """Records what the route asked the Supabase layer to do."""

    def __init__(self, *, written: int | None = None) -> None:
        """`written` forces the confirmed-row count, to fake a partial write."""
        self.saved: list[dict[str, Any]] = []
        self.searches: list[tuple] = []
        self.recents: list[tuple] = []
        self._written = written

    def save(self, rows: list[dict[str, Any]]) -> int:
        """Record the rows and report how many Supabase "confirmed"."""
        self.saved.extend(rows)
        return len(rows) if self._written is None else self._written

    def search(self, query: str, *, machine=None, limit=20) -> list[dict[str, Any]]:
        """Record the search arguments verbatim; always return one hit."""
        self.searches.append((query, machine, limit))
        return [{"id": "mac:s1", "title": "hit"}]

    def recent(self, machine=None, limit=20) -> list[dict[str, Any]]:
        """Record the recent-query arguments verbatim; always return one row."""
        self.recents.append((machine, limit))
        return [{"id": "mac:s1", "title": "recent"}]


def make_convo(monkeypatch) -> tuple[TestClient, Any, FakeStore]:
    """(client, module, store) with auth configured and the lane enabled."""
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setenv("CONVERSATION_SYNC_ENABLED", "1")
    from app.server.routes import conversations
    monkeypatch.setattr(
        conversations.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    store = FakeStore()
    monkeypatch.setattr(
        conversations.conversation_store, "save_conversation_digests", store.save)
    monkeypatch.setattr(
        conversations.conversation_store, "search_conversation_digests", store.search)
    monkeypatch.setattr(
        conversations.conversation_store, "recent_conversation_digests", store.recent)
    app = FastAPI()
    app.include_router(conversations.router)
    return TestClient(app), conversations, store


def ingest_body(digest: str = "hello", title: str = "t") -> dict[str, Any]:
    """One well-formed ingest request body."""
    return {
        "machine": "macbook",
        "digests": [{
            "session_id": "sess-1",
            "project_dir": "/repo",
            "title": title,
            "digest_md": digest,
            "turn_count": 4,
            "started_at": "2026-08-30T01:00:00Z",
            "last_activity_at": "2026-08-30T02:00:00Z",
        }],
    }
