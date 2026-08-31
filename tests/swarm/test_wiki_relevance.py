"""tests/swarm/test_wiki_relevance.py — the relevance gate on wiki ingestion.

`project_requirements` shipped in #697 as a table, a store and two endpoints, and
then had no consumer: `active_requirements()`'s only caller was the endpoint that
read it back out, so the registry influenced no ingestion decision. This module
is that consumer, and these are the first tests over this path.

Two properties carry the weight, and they pull in opposite directions:

  * requirements MUST actually reach the prompt — otherwise the wiring is
    decorative and the registry is still doing nothing
  * the gate MUST NOT be able to fail closed — an empty registry is the state of
    every deployment today AND what a Supabase outage returns, so a gate that
    treated "no basis to judge" as "not relevant" would quarantine the entire
    pipeline on first deploy

Offline by construction: the LLM is an injected callable, the store is
monkeypatched, and the wiki lives in tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from swarm import wiki_relevance  # noqa: E402

REQS = [{"title": "Keep three machines enlisted", "detail": "mesh uptime",
         "keywords": ["mesh", "fleet"]}]


def _llm(payload: str):
    """An injected LLM that records the prompts it was given."""
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return payload

    call.seen = seen  # type: ignore[attr-defined]
    return call


# ── the requirements actually reach the prompt ───────────────────────────────


def test_requirements_reach_the_prompt(monkeypatch):
    """POSITIVE CONTROL for the wiring itself. Deleting the requirements block
    from _build_prompt makes this fail — without it, every other test here would
    still pass while the registry sat unused, which is the exact bug being
    fixed."""
    call = _llm('{"update": [], "create": null, "relevance": 9}')
    wiki_relevance.identify_targets("finding", "index", REQS, call)
    prompt = call.seen[0]  # type: ignore[attr-defined]
    assert "Keep three machines enlisted" in prompt
    assert "mesh uptime" in prompt
    assert "mesh, fleet" in prompt
    assert '"relevance"' in prompt


def test_an_empty_registry_asks_for_no_score(monkeypatch):
    """With nothing to judge against, the prompt must not ask for a relevance
    score at all — a number invented with no basis would then be thresholded
    against as though it meant something."""
    call = _llm('{"update": [], "create": null}')
    wiki_relevance.identify_targets("finding", "index", [], call)
    prompt = call.seen[0]  # type: ignore[attr-defined]
    assert "relevance" not in prompt
    # ...and the rest of the original prompt is untouched.
    assert "update ≤5 files" in prompt
    assert "NEVER include index.md or log.md" in prompt


def test_the_finding_is_still_fenced_but_requirements_are_not():
    """The fencing distinction is the point: the finding is attacker-controlled
    and stays wrapped in untrusted-data delimiters; requirements arrived through
    an authenticated route and must NOT be, or the model is told to disregard the
    very thing it is judging against."""
    call = _llm('{"update": [], "create": null, "relevance": 5}')
    wiki_relevance.identify_targets("HOSTILE-FINDING-TEXT", "index", REQS, call)
    prompt = call.seen[0]  # type: ignore[attr-defined]
    before = prompt.split("HOSTILE-FINDING-TEXT")[0]
    assert "untrusted" in before.lower(), "the finding lost its fence"
    # The requirement text appears outside any fence preamble.
    assert prompt.index("Keep three machines enlisted") < prompt.index("HOSTILE-FINDING-TEXT")


# ── the gate cannot fail closed ──────────────────────────────────────────────


def test_an_empty_registry_skips_the_gate_entirely():
    """THE CRITICAL GREEN CONTROL.

    Every deployment today has an empty registry, and `active_requirements()`
    returns `[]` on a Supabase outage too. If absence counted as irrelevance,
    the first deploy would quarantine every document and a database blip would
    silently stop ingestion. Score 0 here — the most damning possible — must
    still pass, because there was no basis to judge it.
    """
    assert wiki_relevance.below_threshold({"relevance": 0}, []) is False


def test_a_missing_score_counts_as_relevant():
    """Fail-open on a scorer that did not answer. A malformed LLM reply means
    the score is unknown, not that the source is off-topic, and the difference is
    invisible to whoever reviews the quarantine folder later."""
    assert wiki_relevance.below_threshold({}, REQS) is False
    assert wiki_relevance.below_threshold({"relevance": "not-a-number"}, REQS) is False
    assert wiki_relevance.below_threshold({"relevance": None}, REQS) is False


def test_unparseable_llm_output_still_yields_a_usable_result():
    call = _llm("this is not JSON at all")
    out = wiki_relevance.identify_targets("f", "i", REQS, call)
    assert out["update"] == [] and out["create"] is None
    assert out["relevance"] == wiki_relevance.RELEVANCE_MAX


@pytest.mark.parametrize("score,expected", [(0, True), (2, True), (3, False), (10, False)])
def test_the_threshold_boundary(score, expected):
    """3 is the default and is inclusive-pass: `< threshold` quarantines."""
    assert wiki_relevance.below_threshold({"relevance": score}, REQS) is expected


def test_the_threshold_is_env_tunable(monkeypatch):
    monkeypatch.setenv("WIKI_RELEVANCE_THRESHOLD", "8")
    assert wiki_relevance.below_threshold({"relevance": 7}, REQS) is True
    assert wiki_relevance.below_threshold({"relevance": 9}, REQS) is False


def test_a_junk_threshold_falls_back_to_the_default(monkeypatch):
    """A typo'd env var must not make the gate arbitrary."""
    monkeypatch.setenv("WIKI_RELEVANCE_THRESHOLD", "very-high")
    assert wiki_relevance.relevance_threshold() == wiki_relevance.DEFAULT_RELEVANCE_THRESHOLD


@pytest.mark.parametrize("raw,expected", [(-5, 0), (99, 10), ("4", 4), (7.9, 7)])
def test_scores_are_clamped_to_the_scale(raw, expected):
    assert wiki_relevance._coerce_relevance(raw) == expected


# ── project key resolution ───────────────────────────────────────────────────


def test_frontmatter_project_overrides_the_env(monkeypatch):
    """This repo deliberately carries two Linear projects, so a margot clip must
    be able to say so rather than being scored against pi-dev-ops requirements."""
    monkeypatch.setenv("WIKI_PROJECT_KEY", "pi-dev-ops")
    assert wiki_relevance.project_key_for('title: x\nproject: margot\n') == "margot"


def test_the_env_is_used_when_frontmatter_is_silent(monkeypatch):
    monkeypatch.setenv("WIKI_PROJECT_KEY", "margot")
    assert wiki_relevance.project_key_for("title: x\n") == "margot"
    assert wiki_relevance.project_key_for(None) == "margot"


def test_the_default_is_used_when_nothing_is_set(monkeypatch):
    monkeypatch.delenv("WIKI_PROJECT_KEY", raising=False)
    assert wiki_relevance.project_key_for(None) == wiki_relevance.DEFAULT_PROJECT_KEY


@pytest.mark.parametrize("bad", [
    "project: ../../etc/passwd\n",
    "project: has space\n",
    "project:\n",
    "not-project: margot\n",
])
def test_a_malformed_project_key_falls_back_rather_than_being_used(monkeypatch, bad):
    """The key goes into a PostgREST filter. A value that does not match the
    expected shape falls back to the default instead of being passed through."""
    monkeypatch.delenv("WIKI_PROJECT_KEY", raising=False)
    assert wiki_relevance.project_key_for(bad) == wiki_relevance.DEFAULT_PROJECT_KEY


# ── the store never breaks ingestion ─────────────────────────────────────────


def test_fetch_requirements_returns_empty_when_the_store_raises(monkeypatch):
    """A Supabase outage must degrade ingestion to its pre-#697 behaviour, not
    stop it. `[]` then skips the gate via below_threshold()."""
    import app.server.wiki_source_store as store

    def boom(*a: Any, **k: Any):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(store, "active_requirements", boom)
    assert wiki_relevance.fetch_requirements("pi-dev-ops") == []


def test_fetch_requirements_passes_the_project_key_through(monkeypatch):
    """Green control for the test above — without it, a fetch that always
    returned [] would satisfy it while permanently disabling the gate."""
    import app.server.wiki_source_store as store
    seen: list[str] = []

    def fake(project_key: str, limit: int = 50):
        seen.append(project_key)
        return REQS

    monkeypatch.setattr(store, "active_requirements", fake)
    assert wiki_relevance.fetch_requirements("margot") == REQS
    assert seen == ["margot"]
