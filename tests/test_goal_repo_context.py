"""Repo excerpt gathering for goal analysis — honest failure, no invented files."""
from __future__ import annotations

from app.server.goal_repo_context import gather_repo_context


def test_gather_repo_context_reports_limitation_on_http_error() -> None:
    def fake_fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
        return 404, "Not Found"

    out = gather_repo_context("CleanExpo/Synthex", "save a look", fetch=fake_fetch)
    assert out["ok"] is False
    assert out["excerpt"] == ""
    assert "unavailable" in out["limitation"].lower()
    assert "Synthex" in out["limitation"] or "CleanExpo/Synthex" in out["limitation"]


def test_gather_repo_context_reads_tree_and_files() -> None:
    tree = """
    {"tree": [
      {"path": "README.md", "type": "blob"},
      {"path": "app/looks/page.tsx", "type": "blob"},
      {"path": "node_modules/pkg/index.js", "type": "blob"}
    ]}
    """

    def fake_fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
        if "trees" in url:
            return 200, tree
        if url.endswith("README.md"):
            return 200, "# Synthex"
        if "looks/page.tsx" in url:
            return 200, "export default function Looks() { return null }"
        return 404, ""

    out = gather_repo_context("CleanExpo/Synthex", "saved looks page", fetch=fake_fetch)
    assert out["ok"] is True
    assert out["limitation"] == ""
    assert "app/looks/page.tsx" in out["excerpt"]
    assert "node_modules" not in out["excerpt"]
