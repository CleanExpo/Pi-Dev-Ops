"""tests/test_unite_group_wiki.py — Unite-Group wiki_pages reader + graph."""
from __future__ import annotations

import json
from urllib.error import HTTPError

from app.server import unite_group_wiki as UG


def test_resolve_creds_defaults_url_and_ignores_pi_ceo_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_URL", raising=False)
    monkeypatch.delenv("UGO_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", raising=False)
    monkeypatch.delenv("UGO_SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "pi-ceo-key")
    url, key = UG.resolve_creds()
    assert url == UG.DEFAULT_URL
    assert key is None


def test_resolve_creds_accepts_ugo_aliases(monkeypatch):
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_URL", raising=False)
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", raising=False)
    monkeypatch.setenv("UGO_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("UGO_SUPABASE_SERVICE_KEY", "ugo-key")
    url, key = UG.resolve_creds()
    assert url == "https://example.supabase.co"
    assert key == "ugo-key"


def test_build_wiki_graph_resolves_links_and_drops_unknown():
    pages = [
        {
            "id": "alpha",
            "title": "Alpha",
            "tags": ["core"],
            "content": "See [[Beta]] and [[missing]] and [[alpha]].",
            "updated_at": "2026-09-01T00:00:00Z",
        },
        {
            "id": "beta",
            "title": "Beta",
            "tags": None,
            "content": "",
            "updated_at": "2026-09-02T00:00:00Z",
        },
    ]
    graph = UG.build_wiki_graph(pages)
    assert graph["pageCount"] == 2
    assert graph["lastSync"] == "2026-09-02T00:00:00Z"
    assert {n["id"] for n in graph["nodes"]} == {"alpha", "beta"}
    assert graph["edges"] == [{"source": "alpha", "target": "beta"}]
    degrees = {n["id"]: n["degree"] for n in graph["nodes"]}
    assert degrees == {"alpha": 1, "beta": 1}


def test_empty_graph_is_a_stable_200_contract():
    payload = UG.empty_graph("no key")
    assert payload["pageCount"] == 0
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["source"] == "unconfigured"
    assert payload["reason"] == "no key"


def test_fetch_wiki_pages_without_key_does_not_call_network(monkeypatch):
    monkeypatch.delenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", raising=False)
    monkeypatch.delenv("UGO_SUPABASE_SERVICE_KEY", raising=False)

    def fail(*_a, **_k):
        raise AssertionError("network must not run without a key")

    monkeypatch.setattr(UG.urllib.request, "urlopen", fail)
    pages, reason = UG.fetch_wiki_pages()
    assert pages is None
    assert "not configured" in (reason or "")


def test_fetch_wiki_pages_reads_rows(monkeypatch):
    monkeypatch.setenv("UGO_SUPABASE_SERVICE_KEY", "ugo-key")

    class _Resp:
        def read(self) -> bytes:
            return json.dumps([{"id": "a", "title": "A", "tags": [], "content": "", "updated_at": None}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(UG.urllib.request, "urlopen", lambda *_a, **_k: _Resp())
    pages, reason = UG.fetch_wiki_pages()
    assert reason is None
    assert pages is not None and pages[0]["id"] == "a"


def test_fetch_wiki_pages_http_error_is_reason_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_UNITE_GROUP_SERVICE_KEY", "k")

    def boom(*_a, **_k):
        raise HTTPError("https://example.invalid", 404, "missing", hdrs=None, fp=None)

    monkeypatch.setattr(UG.urllib.request, "urlopen", boom)
    pages, reason = UG.fetch_wiki_pages()
    assert pages is None
    assert reason == "wiki_pages read failed (HTTP 404)"
