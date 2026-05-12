"""tests/test_sprinkle_lesson_clusters.py — RA-3017 sprinkle coverage.

Covers `scripts.analyse_lessons._claude_cluster_title`:
  * Routes through provider_router with role `sprinkle.lessons`
  * Returns the trimmed LLM text on success
  * Returns None on empty entry list (no LLM call fires)
  * Returns None on rc != 0
  * Returns None on router-unavailable exception
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests._sprinkle_helpers import FakeProviderRouter, install_fake_router  # noqa: E402


def _load_analyse_lessons():
    """Load scripts/analyse_lessons.py as a module; it isn't on sys.path."""
    path = REPO_ROOT / "scripts" / "analyse_lessons.py"
    spec = importlib.util.spec_from_file_location("analyse_lessons", path)
    assert spec and spec.loader, f"unable to import {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyse_lessons"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def analyse_lessons(monkeypatch, tmp_path: Path):
    mod = _load_analyse_lessons()
    monkeypatch.setattr(mod, "_AUTONOMY_LOG", tmp_path / "autonomy.jsonl")
    return mod


def test_cluster_title_routes_through_provider_router(monkeypatch, analyse_lessons):
    fake = FakeProviderRouter(response="Migration drift between staging and prod")
    install_fake_router(monkeypatch, fake)

    out = analyse_lessons._claude_cluster_title(
        category="deploy",
        entries=[
            {"lesson": "Prisma migration mismatched env"},
            {"lesson": "DB schema diverged after rebase"},
        ],
    )

    assert out == "Migration drift between staging and prod"
    assert len(fake.calls) == 1
    assert fake.calls[0]["role"] == analyse_lessons._CLUSTER_ROLE == "sprinkle.lessons"


def test_cluster_title_returns_none_on_empty_entries(monkeypatch, analyse_lessons):
    fake = FakeProviderRouter(response="should not fire")
    install_fake_router(monkeypatch, fake)

    # All entries have empty `lesson` strings → no snippets → early return.
    out = analyse_lessons._claude_cluster_title(
        category="deploy",
        entries=[{"lesson": ""}, {"lesson": ""}],
    )

    assert out is None
    assert len(fake.calls) == 0


def test_cluster_title_returns_none_on_llm_failure(monkeypatch, analyse_lessons):
    fake = FakeProviderRouter(rc=1, response="", error="model_unavailable")
    install_fake_router(monkeypatch, fake)

    out = analyse_lessons._claude_cluster_title(
        category="security",
        entries=[{"lesson": "Hardcoded creds again"}],
    )

    assert out is None


def test_cluster_title_returns_none_on_router_exception(monkeypatch, analyse_lessons):
    fake = FakeProviderRouter(raise_exc=RuntimeError("ollama down"))
    install_fake_router(monkeypatch, fake)

    out = analyse_lessons._claude_cluster_title(
        category="ux",
        entries=[{"lesson": "Modal-dismiss focus bug recurs"}],
    )

    assert out is None
