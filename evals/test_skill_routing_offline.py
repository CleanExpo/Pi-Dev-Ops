"""Skill routing regression floor, free and keyless: runs on every PR in Prove-It Evals.

Covers every held-out case, both homes: the library's own skills are in skills-library/
(scripts/sync_skills_library.py), so the catalogue here is the one production routes over
(352 skills). The live Jev score comes from .github/workflows/skill-routing-eval.yml.
Floors sit just under the 29/09/2026 measurement on that catalogue (744 held-out cases:
top-1 0.273, recall@254 0.968), so a scoring change that makes the free shortlist worse
fails here. Before the library was synced, only this repo's 175 skills were scored (0.305 /
0.980 over 440 cases); more lookalike skills make the same cases harder, not the scorer worse.
"""
import collections
import json
from pathlib import Path

import pytest

from src.tao import skill_router as sr
from src.tao import skills as tao_skills

CORPUS = Path(__file__).parent / "skill_routing" / "corpus.jsonl"
ROWS = [json.loads(line) for line in CORPUS.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def catalogue():
    return sr.build_catalogue(tao_skills.load_all_skills())


def test_corpus_is_well_formed():
    texts = [r["text"].strip().lower() for r in ROWS]
    assert len(texts) == len(set(texts)), "one label per request text"
    assert {r["split"] for r in ROWS} == {"tune", "heldout"}
    assert sum(r["expected"] is None for r in ROWS) >= 300, "no-skill cases guard against loading for nothing"
    per_skill = collections.Counter(r["expected"] for r in ROWS if r["expected"])
    assert len(per_skill) >= 300 and min(per_skill.values()) >= 6


def test_every_skill_label_exists(catalogue):
    names = {c.name for c in catalogue}
    missing = {r["expected"] for r in ROWS if r["expected"]} - names
    assert missing == set(), f"corpus labels skills Mission Control cannot load: {sorted(missing)}"


def test_free_shortlist_holds_the_right_skill(catalogue):
    held = [r for r in ROWS if r["split"] == "heldout" and r["expected"]]
    assert len(held) >= 700, "the held-out set shrank; re-measure before trusting the floors"
    top1 = recall = 0
    for r in held:
        names = [n for n, _ in sr.shortlist(r["text"], catalogue, sr.MAX_OPTIONS)]
        top1 += bool(names) and names[0] == r["expected"]
        recall += r["expected"] in names
    assert top1 / len(held) >= 0.26, f"lexical top-1 fell to {top1 / len(held):.3f}"
    assert recall / len(held) >= 0.95, f"shortlist recall@{sr.MAX_OPTIONS} fell to {recall / len(held):.3f}"


@pytest.mark.parametrize("cap", ["nan", "inf", "-inf", "-1", "lots"])
def test_the_bench_refuses_a_cap_that_is_not_a_finite_amount(cap):
    """Review P1-DISPATCH-NAN-BYPASSES-SPEND-CAP: a NaN cap made every reservation pass."""
    import argparse

    from evals.skill_routing.run import usd

    with pytest.raises(argparse.ArgumentTypeError):
        usd(cap)
    assert usd("5") == 5.0 and usd("0") == 0.0


def test_the_bench_reads_a_library_skill_whose_name_differs_from_its_folder(tmp_path, monkeypatch):
    """PR #838 CodeRabbit: load_skills rebuilt the path from the frontmatter name, so a skill named
    differently from its folder (graphify -> graphify-windows at library 64d5869) aborted the run."""
    from evals.skill_routing import run

    folder = tmp_path / "skills" / "graphify"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: graphify-windows\ndescription: Graph a repo.\n---\nBody.\n")
    monkeypatch.setattr(tao_skills, "load_all_skills", lambda *a, **k: {})
    assert run.load_skills(tmp_path)["graphify-windows"]["body"] == "Body."


def test_the_bench_refuses_jev_without_a_key(tmp_path, monkeypatch, capsys):
    """PR #838 Bugbot: a missing key reported Jev as NOT RUN and exited 0, so the tune steps looked
    successful and the held-out step crashed later without saying why."""
    import sys

    from evals.skill_routing import run

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["run", "--library", str(tmp_path), "--jev", "--ledger", str(tmp_path / "l")])
    assert run.main() == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err
