"""tests/swarm/test_wiki_ingest_gate.py — the relevance gate inside `ingest()`.

`test_wiki_relevance.py` proves the scoring module decides correctly. These prove
the DECISION IS ACTED ON, which is a separate claim: a gate that scored perfectly
and then wrote the page anyway would pass every test in that file.

So these assert on the FILESYSTEM — what exists in the wiki afterwards, and what
exists in Sources/Quarantine/ — rather than on a returned status. A quarantine
that reported itself but still wrote the page is exactly the failure a
return-value assertion cannot see.

Offline: `_call_llm` and the requirements fetch are both monkeypatched, and the
wiki is a tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from swarm import wiki_ingest  # noqa: E402

REQS = [{"title": "Keep three machines enlisted", "detail": "mesh uptime",
         "keywords": ["mesh"]}]


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    """(wdir, sources, set_llm, set_reqs) — a wiki on disk with both seams faked."""
    wdir = tmp_path / "Wiki"
    wdir.mkdir()
    (wdir / "index.md").write_text("- [[mesh]] — the fleet\n", encoding="utf-8")
    (wdir / "mesh.md").write_text("---\nupdated: 2026-01-01\n---\n\n# Mesh\n", encoding="utf-8")
    sources = tmp_path / "Sources"
    sources.mkdir()
    monkeypatch.setattr(wiki_ingest, "_wiki_dir", lambda: wdir)

    def set_llm(payload: str) -> None:
        monkeypatch.setattr(wiki_ingest, "_call_llm", lambda prompt: payload)

    def set_reqs(rows: list[dict[str, Any]]) -> None:
        monkeypatch.setattr(
            wiki_ingest.wiki_relevance, "fetch_requirements", lambda pk: rows)

    return wdir, sources, set_llm, set_reqs


def _pages(wdir: Path) -> set[str]:
    """Content pages only.

    `log.md` is excluded because it is the append-only audit trail that
    `ingest_guard.quarantine()` writes to — its appearance is the guard working,
    not a stray page. Asserted on separately below.
    """
    return {p.name for p in wdir.glob("*.md") if p.name != "log.md"}


def test_a_low_score_writes_nothing_and_quarantines(wiki):
    """THE CORE CLAIM, asserted on disk.

    The LLM names a real, writable page — so nothing but the relevance gate is
    standing between this finding and a write. The wiki must be byte-for-byte
    unchanged, and the finding must be recoverable from Quarantine/ rather than
    dropped.
    """
    wdir, sources, set_llm, set_reqs = wiki
    before = (wdir / "mesh.md").read_text(encoding="utf-8")
    set_reqs(REQS)
    set_llm('{"update": ["mesh.md"], "create": null, "relevance": 1}')

    result = wiki_ingest.ingest("something entirely unrelated", topic="t")

    assert result.status == "quarantined"
    assert result.pages_updated == [] and result.pages_created == []
    assert (wdir / "mesh.md").read_text(encoding="utf-8") == before, "the page was written"
    assert _pages(wdir) == {"index.md", "mesh.md"}, "a page was created"
    parked = list((sources / "Quarantine").glob("*.md"))
    assert len(parked) == 1, "the finding was dropped rather than parked"
    assert "something entirely unrelated" in parked[0].read_text(encoding="utf-8")
    # The audit trail records WHY, so a mis-scored document is diagnosable
    # months later rather than being an unexplained file in a folder.
    audit = (wdir / "log.md").read_text(encoding="utf-8")
    assert "below relevance threshold" in audit
    assert "pi-dev-ops" in audit


def test_a_high_score_ingests_normally(wiki):
    """GREEN CONTROL. Without it, a gate that quarantined everything would pass
    the test above while silently ending all ingestion."""
    wdir, sources, set_llm, set_reqs = wiki
    set_reqs(REQS)
    set_llm('{"update": ["mesh.md"], "create": null, "relevance": 9}')

    result = wiki_ingest.ingest("a mesh uptime finding", topic="t")

    assert result.status == "ok", result.error
    assert result.pages_updated == ["mesh.md"]
    assert not (sources / "Quarantine").exists() or \
        list((sources / "Quarantine").glob("*.md")) == []


def test_an_empty_registry_ingests_even_a_zero_score(wiki):
    """THE CRITICAL GREEN CONTROL, end to end.

    Empty registry is the state of every deployment today and what a Supabase
    outage returns. Even the most damning possible score must ingest, because
    there was no basis on which to judge it.
    """
    wdir, sources, set_llm, set_reqs = wiki
    set_reqs([])
    set_llm('{"update": ["mesh.md"], "create": null, "relevance": 0}')

    result = wiki_ingest.ingest("anything at all", topic="t")

    assert result.status == "ok", result.error
    assert result.pages_updated == ["mesh.md"]


def test_a_store_outage_does_not_block_ingestion(wiki, monkeypatch):
    """The real fetch path, not a stubbed one: `active_requirements` raising must
    leave ingestion working exactly as it did before #697."""
    wdir, sources, set_llm, _ = wiki
    import app.server.wiki_source_store as store

    def boom(*a: Any, **k: Any):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(store, "active_requirements", boom)
    set_llm('{"update": ["mesh.md"], "create": null, "relevance": 0}')

    result = wiki_ingest.ingest("finding during an outage", topic="t")

    assert result.status == "ok", result.error
    assert result.pages_updated == ["mesh.md"]


def test_the_target_guard_still_runs_on_a_relevant_finding(wiki):
    """Relevance is a ROUTING signal, never a security control. A finding that
    scores maximally still cannot write outside the wiki — `screen()` refuses the
    traversal target and the page is not created."""
    wdir, sources, set_llm, set_reqs = wiki
    set_reqs(REQS)
    set_llm('{"update": ["../../escape.md"], "create": null, "relevance": 10}')

    result = wiki_ingest.ingest("a highly relevant mesh finding", topic="t")

    assert result.pages_updated == []
    assert not (wdir.parent.parent / "escape.md").exists()
    assert _pages(wdir) == {"index.md", "mesh.md"}


def test_the_project_key_reaches_the_requirements_lookup(wiki, monkeypatch):
    """Without this, the key could be computed correctly and then ignored — the
    same class of bug as the registry having no consumer at all."""
    _wdir, _sources, set_llm, _ = wiki
    seen: list[str] = []
    monkeypatch.setattr(
        wiki_ingest.wiki_relevance, "fetch_requirements",
        lambda pk: (seen.append(pk), [])[1])
    set_llm('{"update": [], "create": null}')

    wiki_ingest.ingest("f", topic="t", project_key="margot")

    assert seen == ["margot"]


def test_an_absent_project_key_falls_back_to_the_default(wiki, monkeypatch):
    _wdir, _sources, set_llm, _ = wiki
    monkeypatch.delenv("WIKI_PROJECT_KEY", raising=False)
    seen: list[str] = []
    monkeypatch.setattr(
        wiki_ingest.wiki_relevance, "fetch_requirements",
        lambda pk: (seen.append(pk), [])[1])
    set_llm('{"update": [], "create": null}')

    wiki_ingest.ingest("f", topic="t")

    assert seen == [wiki_ingest.wiki_relevance.DEFAULT_PROJECT_KEY]
