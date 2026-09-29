"""Skill routing regression floor, free and keyless: runs on every PR in Prove-It Evals.

Covers the corpus cases whose skill lives in this repo (the library's skills are not checked
out in keyless CI). The live Jev score comes from .github/workflows/skill-routing-eval.yml.
Floors sit just under the 29/09/2026 measurement (held-out top-1 0.305, recall@254 0.980),
so a scoring change that makes the free shortlist worse fails here.
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


def test_every_repo_skill_label_exists(catalogue):
    names = {c.name for c in catalogue}
    missing = {r["expected"] for r in ROWS if r.get("home") == "pi-dev-ops"} - names
    assert missing == set(), f"corpus labels skills this repo no longer has: {sorted(missing)}"


def test_free_shortlist_holds_the_right_skill(catalogue):
    held = [r for r in ROWS if r["split"] == "heldout" and r.get("home") == "pi-dev-ops"]
    top1 = recall = 0
    for r in held:
        names = [n for n, _ in sr.shortlist(r["text"], catalogue, sr.MAX_OPTIONS)]
        top1 += bool(names) and names[0] == r["expected"]
        recall += r["expected"] in names
    assert top1 / len(held) >= 0.28, f"lexical top-1 fell to {top1 / len(held):.3f}"
    assert recall / len(held) >= 0.96, f"shortlist recall@{sr.MAX_OPTIONS} fell to {recall / len(held):.3f}"


@pytest.mark.parametrize("cap", ["nan", "inf", "-inf", "-1", "lots"])
def test_the_bench_refuses_a_cap_that_is_not_a_finite_amount(cap):
    """Review P1-DISPATCH-NAN-BYPASSES-SPEND-CAP: a NaN cap made every reservation pass."""
    import argparse

    from evals.skill_routing.run import usd

    with pytest.raises(argparse.ArgumentTypeError):
        usd(cap)
    assert usd("5") == 5.0 and usd("0") == 0.0
