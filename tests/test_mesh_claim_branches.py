"""tests/test_mesh_claim_branches.py — the claim queue is read one branch at a time (RA-7910).

Linear ignored the single `filter:{or:[...]}` query: every issue in the workspace
matched, the read ran into _MAX_PAGES on every call and claim/self answered 503
while spending 50 requests a try (measured 05/10: 12 real candidates). Pins:
  * no claim query uses a top-level `or`;
  * both branches are read, every page, and merged without duplicates;
  * an unproven branch still refuses the whole read (strict raises, lax claims nothing).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server import mesh_lanes  # noqa: E402
from app.server.autonomy_eligibility import IncompleteRead  # noqa: E402


def _node(ident: str) -> dict:
    return {"id": ident, "identifier": ident}


class FakeLinear:
    """Serves pages per branch: {branch_index: [[nodes page1], [nodes page2], ...]}."""

    def __init__(self, pages: dict[int, list[list[dict]]]):
        self.pages = pages
        self.calls: list[str] = []

    def __call__(self, query: str) -> dict:
        self.calls.append(query)
        branch = next(i for i, f in enumerate(mesh_lanes._BRANCH_FILTERS) if f in query)
        n = query.count("after:")  # page index: 0 for the first page
        if "after:" in query:
            n = int(query.split('after:"p')[1].split('"')[0])
        rows = self.pages[branch]
        more = n + 1 < len(rows)
        return {"issues": {"nodes": rows[n], "pageInfo": {"hasNextPage": more,
                                                          "endCursor": f"p{n + 1}" if more else None}}}


@pytest.fixture(autouse=True)
def _everything_eligible(monkeypatch):
    monkeypatch.setattr(mesh_lanes, "eligible", lambda n, repos: True)
    monkeypatch.setattr(mesh_lanes, "registry_repos", lambda: {})


def test_no_claim_query_uses_a_top_level_or():
    assert len(mesh_lanes.SELF_CLAIM_QUERIES) == 2
    for q in mesh_lanes.SELF_CLAIM_QUERIES:
        assert "or:[" not in q.replace(" ", "")
        assert q.count(mesh_lanes._PAGE_ARGS) == 1


def test_both_branches_every_page_merged_once():
    fake = FakeLinear({0: [[_node("A"), _node("B")], [_node("C")]],
                       1: [[_node("B"), _node("D")]]})
    nodes, _ = mesh_lanes.candidates(fake, strict=True)
    assert sorted(n["identifier"] for n in nodes) == ["A", "B", "C", "D"]
    assert len(fake.calls) == 3  # two pages of branch 0, one of branch 1


def test_an_unreadable_branch_refuses_the_whole_read():
    def broken(query):
        if mesh_lanes._BRANCH_FILTERS[1] in query:
            return {}  # Linear failed: no issues connection
        return {"issues": {"nodes": [_node("A")], "pageInfo": {"hasNextPage": False}}}
    with pytest.raises(IncompleteRead):
        mesh_lanes.candidates(broken, strict=True)
    assert mesh_lanes.candidates(broken)[0] == []


def test_a_branch_that_never_ends_is_refused_not_truncated(monkeypatch):
    monkeypatch.setattr(mesh_lanes, "_MAX_PAGES", 3)
    endless = FakeLinear({0: [[_node(f"X{i}")] for i in range(10)], 1: [[]]})
    with pytest.raises(IncompleteRead):
        mesh_lanes.candidates(endless, strict=True)
