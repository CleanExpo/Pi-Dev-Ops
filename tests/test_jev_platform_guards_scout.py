"""Guard sweep 29/09: every scout.py guard has a test that fails when the guard is removed. Offline only."""
from __future__ import annotations

import pytest
from jev_scale_support import GOOD, Recorder, budget, make_repo

from jev_platform import scout

TID = "pick-first-for-task"
FILES = {"src/domain/billing.ts": GOOD, "src/http/routes.ts": "export const r = 1;\n"}


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path, FILES)


def reply(answers: dict):
    return Recorder(lambda body: {"model": "jev-1", "answers": answers})


def choice(choice="f001", confidence=0.9, probs=None, type_="choice") -> dict:
    return {"type": type_, "choice": choice, "confidence": confidence,
            "probabilities": {"f001": 0.9} if probs is None else probs}


def pick(repo, post, candidates=("src/http/routes.ts",)):
    return scout.pick_first(repo, "p3", TID, list(candidates), post, budget())


@pytest.mark.parametrize("answers", [
    {TID: choice(), "extra-id": choice()},                    # an id nobody asked about
    {TID: choice(type_="noul")},                              # wrong answer type
    {TID: choice(confidence=1.5)},                            # confidence outside [0, 1]
    {TID: choice(probs={"f001": 2.0})},                       # probability outside [0, 1]
    {TID: choice(probs={"f001": 0.8, "f999": 0.1})},          # probability for a key never sent
])
def test_pick_answer_that_breaks_any_shape_rule_is_unavailable_without_numbers(repo, answers):
    """guard sweep 29/09: each clause of _pick_answer refuses on its own; no path or numbers leak out."""
    out = pick(repo, reply(answers))
    assert out["outcome"] == "unavailable" and out["reason"] == "signal_unavailable:invalid_response"
    assert not ({"confidence", "probabilities", "path"} & set(out))


def test_pick_choice_outside_the_sent_keys_is_unavailable_even_when_probabilities_are_clean(repo):
    """guard sweep 29/09: the choice check stands alone; the probability-key check does not cover it."""
    out = pick(repo, reply({TID: choice(choice="f999", probs={"f001": 0.9})}))
    assert out["outcome"] == "unavailable" and "path" not in out


def test_denied_name_listed_in_the_manifest_is_still_refused_as_a_pick_candidate(tmp_path):
    """guard sweep 29/09: an approved `.env` never becomes a keyed candidate, so nothing is sent."""
    repo = make_repo(tmp_path, {**FILES, ".env": "PLAIN=1\n"})
    post = Recorder()
    out = pick(repo, post, [".env"])
    assert out["refused"] == [{"path": ".env", "reason": "not an approved path"}] and out["outcome"] == "none"
    assert post.calls == []


def test_denied_name_is_absent_from_the_sent_files_beside_a_good_candidate(tmp_path):
    """guard sweep 29/09: the same guard, seen from the wire."""
    repo = make_repo(tmp_path, {**FILES, ".env": "PLAIN=1\n"})
    post = Recorder(lambda body: {"model": "jev-1", "answers": {TID: choice()}})
    pick(repo, post, [".env", "src/http/routes.ts"])
    assert post.calls[0]["state"]["files"] == {"f001": "src/http/routes.ts"}


@pytest.mark.parametrize("paths", [["src/http/routes.ts", "src/http/routes.ts"], []])
def test_ask_jev_bundle_of_duplicate_or_no_paths_is_refused_with_zero_requests(repo, paths):
    """guard sweep 29/09: 1-20 DISTINCT paths; a duplicate or an empty bundle never reaches Jev."""
    post = Recorder()
    out = scout.ask_jev(repo, "p3", paths, ["triage-bundle"], post, budget())
    assert out == {"outcome": "refused", "reason": f"need 1-{scout.MAX_BUNDLE} distinct paths"} and post.calls == []


def test_ask_jev_http_failure_is_unavailable_with_the_digests_kept_locally(repo):
    """guard sweep 29/09: no data means unavailable, never an answer."""
    out = scout.ask_jev(repo, "p3", ["src/http/routes.ts"], ["triage-bundle"], Recorder(status=503), budget())
    assert out["outcome"] == "unavailable" and out["reason"] == "signal_unavailable:http_503"
    assert "answers" not in out and set(out["sha256"]) == {"src/http/routes.ts"}
