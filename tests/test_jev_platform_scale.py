"""Offline controls for Level 9 (jev_platform.scout: ask_jev_files, pick_first_file), PLAN-scale.md rev 5.

Every refusal asserts ZERO requests. C13 counts the tests named `cap_255` / `pick_first_only_real_path`.
"""
from __future__ import annotations

import json
import re
import subprocess

import pytest
from jev_scale_support import GOOD, PROMPTS, TEMPLATES, Recorder, answer_all, budget, make_repo, sha

from jev_platform import ask, client, committed, scout


@pytest.fixture
def repo(tmp_path):
    files = {"src/domain/billing.ts": GOOD, "src/http/routes.ts": "export const r = 1;\n",
             "src/auth/none": "export const n = 0;\n"}
    return make_repo(tmp_path, files)


@pytest.fixture(scope="module")
def big_repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("big")
    return make_repo(root, {f"src/m{i:03d}.ts": f"export const v{i} = {i};\n" for i in range(300)})


def test_cap_255_sends_255_and_skips_45_with_the_cap_reason(big_repo):
    post = Recorder()
    out = scout.scout_files(big_repo, ["src/**/*.ts"], ["known-issue"], post, budget(0.75))
    capped = [s for s in out["skipped"] if s["reason"] == scout.CAP_REASON]
    assert len(post.calls) == 255 and len(out["results"]) == 255 and len(capped) == 45


def test_glob_never_yields_an_unapproved_path_even_on_disk(tmp_path):
    repo = make_repo(tmp_path, {"src/a.ts": GOOD, "src/secret_plan.ts": GOOD}, approved={"src/a.ts": GOOD})
    post = Recorder()
    out = scout.scout_files(repo, ["src/**"], ["known-issue"], post, budget())
    seen = json.dumps(out) + json.dumps(post.calls)
    assert [r["path"] for r in out["results"]] == ["src/a.ts"] and "secret_plan" not in seen


def test_request_body_is_rebuilt_byte_for_byte_from_reviewed_parts(repo):
    post = Recorder()
    scout.scout_files(repo, ["src/domain/*.ts"], ["relevant-to-task", "known-issue"], post, budget(), prompt_id="p3")
    q = ask.build_questions(json.loads(open(f"{repo}/{ask.MANIFEST}").read()), ["relevant-to-task", "known-issue"])[0]
    expected = {"state": {"task": PROMPTS["p3"], "content": GOOD}, "model": "jev-latest", "questions": q}
    assert [json.dumps(b) for b in post.calls] == [json.dumps(expected)]


@pytest.mark.parametrize("call", [
    lambda repo, post: scout.scout_files(repo, ["src/**"], ["known-issue"], post, budget(), prompt_id="free text"),
    lambda repo, post: scout.pick_first(repo, "Fix the rounding bug", "pick-first-for-task", ["src/http/routes.ts"],
                                        post, budget()),
    lambda repo, post: scout.ask_jev(repo, "nope", ["src/http/routes.ts"], ["triage-bundle"], post, budget()),
    lambda repo, post: scout.pick_first(repo, None, "pick-first-for-task", ["src/http/routes.ts"], post, budget()),
])
def test_unknown_or_free_text_prompt_is_refused_with_zero_requests(repo, call):
    post = Recorder()
    out = call(repo, post)
    assert "prompt" in (out.get("blocked") or out.get("reason")) and post.calls == []


def test_prune_reasons_and_changed_bytes_are_reported(tmp_path):
    files = {"a.ts": GOOD, ".env": "PLAIN=1\n", "b.ts": "const b = 2;\n",
             "leak.ts": "const k = 'AKIAABCDEFGHIJKLMNOP';\n"}
    repo = make_repo(tmp_path, files)
    (tmp_path / "b.ts").write_text("const b = 3;\n")
    post = Recorder()
    out = scout.scout_files(repo, ["*", ".*"], ["known-issue"], post, budget())
    reasons = {s["path"]: s["reason"] for s in out["skipped"]}
    assert reasons == {".env": "denied path", "b.ts": "content differs from approved sha256",
                       "leak.ts": "sensitive content"}
    assert [b["state"]["content"] for b in post.calls] == [GOOD]


def test_small_budget_lists_the_rest_as_budget_exhausted(big_repo):
    post = Recorder()
    out = scout.scout_files(big_repo, ["src/m00*.ts"], ["known-issue"], post, budget(0.01))
    exhausted = [s for s in out["skipped"] if s["reason"] == "budget exhausted"]
    assert len(post.calls) == 3 and len(out["results"]) == 3 and len(exhausted) == 7


def test_scout_result_keeps_sha256_locally_and_marks_unavailable(repo):
    out = scout.scout_files(repo, ["src/domain/*"], ["known-issue"], Recorder(status=503), budget())
    r = out["results"][0]
    assert r["sha256"] == sha(GOOD) and r["unavailable"] == "signal_unavailable:http_503" and "answers" not in r


def pick_reply(choice, confidence=0.9, probs=None):
    def reply(body):
        return {"model": "jev-1", "answers": {"pick-first-for-task": {
            "type": "choice", "choice": choice, "confidence": confidence,
            "probabilities": probs if probs is not None else {choice: confidence}}}}
    return reply


def pick(repo, candidates, post, floor=0.3):
    return scout.pick_first(repo, "p3", "pick-first-for-task", candidates, post, budget(), floor)


@pytest.mark.parametrize("choice", ["f009", "src/domain/billing.ts"])
def test_pick_first_only_real_path_key_outside_sent_set_is_unavailable(repo, choice):
    out = pick(repo, ["src/domain/billing.ts", "src/http/routes.ts"], Recorder(pick_reply(choice)))
    assert out["outcome"] == "unavailable" and "confidence" not in out and "path" not in out


def test_pick_first_picks_the_keyed_path(repo):
    post = Recorder(pick_reply("f002", 0.8, {"f001": 0.2, "f002": 0.8}))
    out = pick(repo, ["src/http/routes.ts", "src/domain/billing.ts"], post)
    assert out["outcome"] == "picked" and out["path"] == "src/domain/billing.ts" and out["confidence"] == 0.8
    assert post.calls[0]["state"] == {"task": PROMPTS["p3"],
                                      "files": {"f001": "src/http/routes.ts", "f002": "src/domain/billing.ts"}}


@pytest.mark.parametrize("choice, confidence", [("none", 0.9), ("other", 0.9), ("f001", 0.2)])
def test_pick_first_none_other_or_low_confidence_is_none_with_numbers(repo, choice, confidence):
    out = pick(repo, ["src/http/routes.ts"], Recorder(pick_reply(choice, confidence)))
    assert out["outcome"] == "none" and out["confidence"] == confidence and "probabilities" in out


@pytest.mark.parametrize("post", [Recorder(lambda b: {"answers": {}}), Recorder(status=500),
                                  Recorder(pick_reply("f001", float("nan")))])
def test_pick_first_malformed_or_failed_is_unavailable_without_numbers(repo, post):
    out = pick(repo, ["src/http/routes.ts"], post)
    assert out["outcome"] == "unavailable" and not ({"confidence", "probabilities", "path"} & set(out))


def test_pick_first_dedupes_keys_a_file_named_none_and_refuses_unapproved(repo):
    post = Recorder(pick_reply("none"))
    out = pick(repo, ["src/auth/none", "src/auth/none", "src/http/routes.ts", "nope.ts"], post)
    files = post.calls[0]["state"]["files"]
    assert files == {"f001": "src/auth/none", "f002": "src/http/routes.ts"}
    assert set(post.calls[0]["questions"]["pick-first-for-task"]["criteria"]) == {"f001", "f002", "none"}
    assert out["refused"] == [{"path": "nope.ts", "reason": "not an approved path"}]


def test_pick_first_caps_at_250_and_empty_is_none_with_zero_requests(big_repo):
    post = Recorder(pick_reply("f001"))
    out = pick(big_repo, [f"src/m{i:03d}.ts" for i in range(300)], post)
    assert len(post.calls[0]["state"]["files"]) == 250 and len(out["refused"]) == 50
    empty = Recorder()
    assert pick(big_repo, [], empty) == {"outcome": "none", "reason": "no candidates", "requests": 0, "refused": []}
    assert empty.calls == []


def test_git_subprocess_gets_a_minimal_env_without_keys(repo, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-fake-value")
    monkeypatch.setenv("TYPESAFE_API_KEY", "t-fake-value")
    seen, real_run, real_popen = [], subprocess.run, subprocess.Popen

    def spy(real):
        def call(*args, **kwargs):
            seen.append(kwargs.get("env"))
            return real(*args, **kwargs)
        return call
    monkeypatch.setattr(committed.subprocess, "run", spy(real_run))  # the manifest is read through committed.py
    monkeypatch.setattr(committed.subprocess, "Popen", spy(real_popen))
    assert ask.approved_manifest(repo) is not None
    assert len(seen) >= 2 and all(e is not None and not any(re.search("KEY|TOKEN|SECRET", k) for k in e) for e in seen)


def test_planted_secret_with_refreshed_digest_is_still_refused(tmp_path):
    text = "const token = 'ghp_abcdefghijklmnopqrstuvwxyz';\n"
    repo = make_repo(tmp_path, {"cfg.ts": text})
    post = Recorder()
    out = scout.scout_files(repo, ["*.ts"], ["known-issue"], post, budget())
    assert out["skipped"] == [{"path": "cfg.ts", "reason": "sensitive content"}] and post.calls == []


def test_guarded_send_refuses_a_sensitive_body_before_the_wire():
    post = Recorder()
    out = scout.guarded_send({"state": {"content": "mail me at a@b.co"}}, post, client.Budget(0.1, 60))
    assert out == {"error": "refused: sensitive payload"} and post.calls == []


def test_templates_fixture_is_valid():
    from jev_platform import manifest as mf
    assert all(mf.template_problem(t, v) is None for t, v in TEMPLATES.items()) and answer_all
