"""Guard sweep 29/09: one offline control per jev_platform.ask guard that no test used to reach.

Each test fails with its guard removed (tests/mutation/jev_platform_mutants.py) and every refusal asserts
ZERO requests. No network, no keys: `post` is a recording fake.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from jev_scale_support import GOOD, TEMPLATES, Recorder, answer_all, budget, git, make_repo, sha

from jev_platform import __main__ as cli
from jev_platform import ask


def commit_manifest(tmp_path, manifest) -> str:
    """A repo whose committed .jev-approved.json is exactly `manifest` (any JSON value)."""
    (tmp_path / "a.ts").write_text(GOOD)
    (tmp_path / ask.MANIFEST).write_text(json.dumps(manifest))
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-f", ".")
    git(tmp_path, "commit", "-qm", "fixture")
    return str(tmp_path)


def ask_one(repo, tids, post, path="src/a.ts"):
    return ask.ask_files(repo, [path], tids, post, budget())


@pytest.mark.parametrize("value", [[], ["files", "questions"], "x", 1, None])
def test_a_committed_manifest_that_is_not_an_object_is_refused(tmp_path, value):
    """Guard sweep 29/09 bug fix: a JSON list/str/number/null manifest raised AttributeError; it must refuse."""
    post = Recorder()
    out = ask.ask_files(commit_manifest(tmp_path, value), ["a.ts"], ["known-issue"], post, budget())
    assert out["blocked"].startswith("no committed") and post.calls == []


@pytest.mark.parametrize("value", [{"files": {"a.ts": sha(GOOD)}}, {"files": {"a.ts": sha(GOOD)}, "questions": []},
                                   {"files": [], "questions": TEMPLATES}])
def test_a_manifest_without_files_and_questions_objects_is_refused(tmp_path, value):
    """Guard sweep 29/09: both halves of the shape check (files dict, questions dict)."""
    post = Recorder()
    out = ask.ask_files(commit_manifest(tmp_path, value), ["a.ts"], ["known-issue"], post, budget())
    assert out["blocked"].startswith("no committed") and post.calls == []


def test_file_over_the_cap_is_refused_even_when_approved_by_approve_entry(tmp_path):
    """Guard sweep 29/09: a 40,000-byte file approved with `approve_entry`'s own digest is never sent.
    Kills both the size check and the +1 read that lets the size check see an oversize file."""
    big = "x" * 40_000
    repo = make_repo(tmp_path, {"big.txt": big}, approved={})
    entry = ask.approve_entry(repo, "big.txt")
    assert entry == {"big.txt": hashlib.sha256(big[:ask.MAX_FILE_BYTES + 1].encode()).hexdigest()}
    m = json.loads((tmp_path / ask.MANIFEST).read_text())
    m["files"].update(entry)
    (tmp_path / ask.MANIFEST).write_text(json.dumps(m))
    git(tmp_path, "commit", "-qam", "approve big")
    post = Recorder()
    r = ask_one(repo, ["known-issue"], post, "big.txt")["results"][0]
    assert r["refused"] == "file over 32,000 bytes" and post.calls == []


def test_file_over_the_cap_approved_at_its_first_32000_bytes_is_refused(tmp_path):
    """Guard sweep 29/09: an approval of the truncated prefix must not let the oversize file through."""
    big = "y" * 40_000
    repo = make_repo(tmp_path, {"big.txt": big}, approved={"big.txt": big[:ask.MAX_FILE_BYTES]})
    post = Recorder()
    r = ask_one(repo, ["known-issue"], post, "big.txt")["results"][0]
    assert r["refused"] == "file over 32,000 bytes" and post.calls == []


def test_approve_refuses_a_path_escaping_the_repo(tmp_path):
    """Guard sweep 29/09: `approve` reads with no manifest admission, so read_confined alone must refuse `..`."""
    (tmp_path / "out.txt").write_text("outside the repo\n")
    (tmp_path / "repo").mkdir()
    repo = make_repo(tmp_path / "repo", {"a.ts": GOOD})
    with pytest.raises(ValueError, match="relative, without"):
        cli.main(["approve", "../out.txt", "--repo", repo])


def nine_templates() -> dict:
    return {f"q{i}": {"type": "noul", "question": f"Is `content` item {i}?", "true": "yes", "false": "no"}
            for i in range(9)}


BAD_TEMPLATES = {
    "noul-criteria-not-text": {"type": "noul", "question": "Is `content` ok?", "true": 1, "false": "no"},
    "noul-question-not-text": {"type": "noul", "question": 7, "true": "yes", "false": "no"},
    "choice-one-option": {"type": "choice", "question": "Which is `content`?", "options": {"only": "one"}},
    "choice-256-options": {"type": "choice", "question": "Which is `content`?",
                           "options": {f"o{i}": "d" for i in range(256)}},
    "choice-option-not-text": {"type": "choice", "question": "Which is `content`?", "options": {"a": "x", "b": 1}},
}


@pytest.mark.parametrize("tid", sorted(BAD_TEMPLATES))
def test_malformed_template_is_blocked_before_any_request(tmp_path, tid):
    """Guard sweep 29/09: _question's type checks on noul criteria and choice options."""
    repo = make_repo(tmp_path, {"src/a.ts": GOOD}, questions={**TEMPLATES, tid: BAD_TEMPLATES[tid]})
    post = Recorder()
    out = ask_one(repo, [tid], post)
    assert out["blocked"] == f"unknown or malformed template: {tid}" and post.calls == []


def test_nine_valid_templates_are_blocked(tmp_path):
    """Guard sweep 29/09: more than MAX_QUESTIONS templates are refused even when every one is valid."""
    templates = nine_templates()
    repo = make_repo(tmp_path, {"src/a.ts": GOOD}, questions=templates)
    post = Recorder()
    out = ask_one(repo, sorted(templates), post)
    assert out["blocked"] == "need 1-8 templates" and post.calls == []
    assert "results" in ask_one(repo, sorted(templates)[:8], Recorder())  # eight is fine: the fixture is valid


@pytest.mark.parametrize("template", [
    {"type": "noul", "question": "Is `content` " + "long " * 240 + "?", "true": "yes", "false": "no"},
    {"type": "noul", "question": "Does `content` apply the drying goal per IICRC S500?", "true": "yes", "false": "no"},
    {"type": "noul", "question": "Does `content` quote Standards Australia?", "true": "yes", "false": "no"},
])
def test_long_or_sensitive_template_is_refused_before_any_request(tmp_path, template):
    """Guard sweep 29/09: template text over MAX_TEMPLATE_CHARS, or naming a banned publisher, is never sent."""
    repo = make_repo(tmp_path, {"src/a.ts": GOOD}, questions={**TEMPLATES, "bad": template})
    post = Recorder()
    out = ask_one(repo, ["bad"], post)
    assert out["blocked"] == "template refused: bad" and post.calls == []


def reply_with(tid, answer):
    def resp(body):
        d = answer_all(body)
        d["answers"][tid] = answer
        return d
    return resp


@pytest.mark.parametrize("tid, answer", [
    ("known-issue", {"type": "choice", "noul": 0.9}),
    ("known-issue", {"type": "noul", "noul": 1.5}),
    ("known-issue", {"type": "noul", "noul": "0.9"}),
    ("known-issue", {"type": "noul", "noul": True}),
    ("layer", {"type": "noul", "choice": "domain_logic", "confidence": 0.9, "probabilities": {"domain_logic": 0.9}}),
    ("layer", {"type": "choice", "choice": "domain_logic", "confidence": 0.9,
               "probabilities": {"domain_logic": 0.8, "made_up": 0.1}}),
    ("layer", {"type": "choice", "choice": "domain_logic", "confidence": 0.9, "probabilities": {"domain_logic": 1.5}}),
    ("layer", {"type": "choice", "choice": "domain_logic", "confidence": 0.9,
               "probabilities": {"domain_logic": float("nan")}}),
])
def test_wrong_type_or_out_of_range_answer_is_unavailable_with_no_numbers(tmp_path, tid, answer):
    """Guard sweep 29/09: answer type must match the question; noul and every probability must be valid NOUL;
    probability keys must be options or `other`. Everything else about the reply is valid."""
    repo = make_repo(tmp_path, {"src/a.ts": GOOD})
    post = Recorder(reply_with(tid, answer))
    r = ask_one(repo, [tid], post)["results"][0]
    assert len(post.calls) == 1
    assert r["unavailable"] == "signal_unavailable:invalid_response" and "answers" not in r


def test_the_valid_reply_fixture_is_answered(tmp_path):
    """Guard sweep 29/09 positive control: the reply the tests above corrupt is accepted when left alone."""
    repo = make_repo(tmp_path, {"src/a.ts": GOOD})
    r = ask_one(repo, ["known-issue", "layer"], Recorder())["results"][0]
    assert set(r["answers"]) == {"known-issue", "layer"} and r["note"] == ask.ADVISORY


@pytest.mark.parametrize("tid", ["sk-reviewfixtureabcdefgh", "customer@example.test"])
def test_a_sensitive_template_id_is_refused_before_any_request(tmp_path, tid):
    """Round 19 P1-ASK-TEMPLATE-ID-DISCLOSURE: the id is sent as a questions key, so it is screened like the text."""
    repo = make_repo(tmp_path, {"src/a.ts": GOOD}, questions={**TEMPLATES, tid: TEMPLATES["known-issue"],
                                                              "plain-copy": TEMPLATES["known-issue"]})
    post = Recorder()
    assert ask_one(repo, ["plain-copy"], post)["results"] and len(post.calls) == 1  # control: the template is sent
    post = Recorder()
    assert ask_one(repo, [tid], post)["blocked"] == f"template refused: {tid}" and post.calls == []
