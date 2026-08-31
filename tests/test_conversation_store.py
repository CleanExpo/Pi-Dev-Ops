"""tests/test_conversation_store.py — the Supabase layer under the routes.

Split from `test_conversations_api.py`, which covers the HTTP surface: these
exercise `app.server.conversation_store` directly, monkeypatching
`supabase_log._request`, so they assert on the PostgREST path that gets built
rather than on a response body.

The load-bearing one is `test_a_search_term_cannot_widen_the_query`. Search text
reaches a filter built by f-string interpolation, where an unescaped `&` starts a
new filter parameter and an unescaped `=` splits the operator — so a crafted term
would broaden the read instead of erroring, and a broadened read is silent.

Fully offline: no test here may make a request.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def test_empty_tsquery_returns_nothing_rather_than_everything(monkeypatch):
    """A punctuation-only query must NOT degrade into an unfiltered select — a
    search box quietly returning the whole table looks exactly like a working
    search."""
    from app.server import conversation_store
    monkeypatch.setattr(
        conversation_store.supabase_log, "_request",
        lambda *a, **k: pytest.fail("no request should be made for an empty tsquery"))
    assert conversation_store.search_conversation_digests("   ??? ") == []


@pytest.mark.parametrize("hostile", [
    "x&limit=1000&select=*",          # a second filter parameter
    "machine=eq.other",               # an operator split
    "a' OR '1'='1",                   # SQL-shaped
    "'; drop table conversation_digests; --",
    "foo|bar!baz&qux",                # tsquery operators
])
def test_a_search_term_cannot_widen_the_query(hostile, monkeypatch):
    """Search text reaches a PostgREST filter built by f-string interpolation.

    An unescaped `&` there starts a NEW filter parameter and an unescaped `=`
    splits the operator, so a crafted term would BROADEN the query rather than
    error — and a broadened read is silent. Two things stop it: `_tsquery`
    keeps only `[A-Za-z0-9_]+` tokens, and `_q` percent-encodes what survives.
    Both were verified by probing, but neither was pinned, so widening the token
    regex later (to support quoted phrases, say) would quietly reopen this.
    """
    from app.server import conversation_store as cs
    seen: dict[str, str] = {}

    def fake_request(method, path, body=None, prefer=""):
        seen["path"] = path
        return 200, []

    # Layer 1, checked BEFORE encoding. Asserting only on the final URL would
    # not test this: `_q` percent-encodes `&` and `=`, so a widened token regex
    # still yields a clean-looking URL and the assertion passes for the wrong
    # reason. Verified — widening the regex to `[^\s]+` left a URL-only check
    # green.
    tsq = cs._tsquery(hostile)
    assert set(tsq) <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_&"), \
        f"_tsquery let a metacharacter through: {tsq!r}"

    # Layer 2: what actually reaches the filter.
    monkeypatch.setattr(cs.supabase_log, "_request", fake_request)
    cs.search_conversation_digests(hostile, limit=5)
    path = seen["path"]
    value = path.split("search_tsv=fts(english).")[1].split("&")[0]
    assert "=" not in value and "&" not in value, f"term escaped into the filter: {value!r}"
    assert path.count("select=") == 1 and path.count("limit=") == 1
    assert "machine=" not in path, "a term forged a machine filter"


def test_search_builds_an_fts_filter_on_the_generated_column(monkeypatch):
    from app.server import conversation_store
    seen: dict[str, str] = {}

    def fake_request(method, path, body=None, prefer=""):
        seen["method"], seen["path"] = method, path
        return 200, [{"id": "m:s"}]

    monkeypatch.setattr(conversation_store.supabase_log, "_request", fake_request)
    rows = conversation_store.search_conversation_digests(
        "auth/session token", machine="nas", limit=999)
    assert rows == [{"id": "m:s"}]
    assert seen["method"] == "GET"
    assert "search_tsv=fts(english)." in seen["path"]
    assert "auth%26session%26token" in seen["path"]
    assert "machine=eq.nas" in seen["path"]
    assert "limit=100" in seen["path"]  # clamped


def test_save_returns_rows_confirmed_not_rows_sent(monkeypatch):
    from app.server import conversation_store

    def fake_request(method, path, body=None, prefer=""):
        assert "resolution=merge-duplicates" in prefer
        assert "return=representation" in prefer
        return 201, [{"id": "m:s1"}]  # only one of two confirmed

    monkeypatch.setattr(conversation_store.supabase_log, "_request", fake_request)
    assert conversation_store.save_conversation_digests(
        [{"id": "m:s1"}, {"id": "m:s2"}]) == 1


def test_save_returns_zero_when_supabase_unconfigured(monkeypatch):
    from app.server import conversation_store
    monkeypatch.setattr(
        conversation_store.supabase_log, "_request", lambda *a, **k: (0, None))
    assert conversation_store.save_conversation_digests([{"id": "m:s1"}]) == 0


def test_reads_never_raise_on_failure(monkeypatch):
    from app.server import conversation_store
    monkeypatch.setattr(
        conversation_store.supabase_log, "_request", lambda *a, **k: (500, None))
    assert conversation_store.search_conversation_digests("deploy") == []
    assert conversation_store.recent_conversation_digests() == []
