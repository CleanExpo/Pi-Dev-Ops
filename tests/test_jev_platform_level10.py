"""Offline controls for Level 10 (scout.ask_jev), template/state compatibility, manifest load and bulk approval.

PLAN-scale.md rev 5. Every refusal asserts ZERO requests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jev_scale_support import GOOD, PROMPTS, TEMPLATES, Recorder, budget, make_repo, sha

from jev_platform import __main__ as cli
from jev_platform import ask, manifest, scout

FILES = {"src/domain/billing.ts": GOOD, "src/http/routes.ts": "export const r = 1;\n"}


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path, FILES)


def run_tool(tool, repo, post, tids):
    if tool == "scout":
        return scout.scout_files(repo, ["src/domain/*"], tids, post, budget())
    if tool == "scout+task":
        return scout.scout_files(repo, ["src/domain/*"], tids, post, budget(), prompt_id="p3")
    if tool == "pick":
        return scout.pick_first(repo, "p3", tids[0], ["src/domain/billing.ts"], post, budget())
    return scout.ask_jev(repo, "p3", ["src/domain/billing.ts"], tids, post, budget())


SHAPE = {"scout": {"content"}, "scout+task": {"task", "content"}, "pick": {"task", "files"}, "ask": {"task", "files"}}


@pytest.mark.parametrize("tool, tids", [("scout", ["known-issue", "layer"]), ("scout+task", ["relevant-to-task"]),
                                        ("pick", ["pick-first-for-task"]), ("ask", ["triage-bundle"])])
def test_compatible_template_sends_the_tools_documented_state_shape(repo, tool, tids):
    post = Recorder()
    run_tool(tool, repo, post, tids)
    assert len(post.calls) == 1 and set(post.calls[0]["state"]) == SHAPE[tool]
    assert all(set(manifest.template_state(TEMPLATES[t])) <= SHAPE[tool] for t in tids)


def test_prompt_id_with_content_only_template_sends_task_and_content(repo):
    post = Recorder()
    run_tool("scout+task", repo, post, ["known-issue"])
    assert post.calls[0]["state"] == {"task": PROMPTS["p3"], "content": GOOD}


def test_prompt_id_with_a_mixed_batch_sends_one_body_holding_both(repo):
    post = Recorder()
    out = run_tool("scout+task", repo, post, ["known-issue", "relevant-to-task"])
    assert len(post.calls) == 1 and set(post.calls[0]["questions"]) == {"known-issue", "relevant-to-task"}
    assert set(post.calls[0]["state"]) == {"task", "content"} and "answers" in out["results"][0]


@pytest.mark.parametrize("tool, tid", [("scout", "relevant-to-task"), ("scout", "triage-bundle"),
                                       ("scout+task", "triage-bundle"), ("pick", "known-issue"),
                                       ("pick", "triage-bundle"), ("ask", "relevant-to-task"), ("ask", "layer")])
def test_incompatible_template_is_refused_with_zero_requests(repo, tool, tid):
    post = Recorder()
    out = run_tool(tool, repo, post, [tid])
    reason = out.get("blocked") or out.get("reason")
    assert post.calls == [] and ("reads" in reason or "not a pick template" in reason)


def test_incompatible_refusal_names_the_fields(repo):
    out = run_tool("scout", repo, Recorder(), ["relevant-to-task"])
    assert out["blocked"] == "refused: template relevant-to-task reads task, content, this tool sends content"


@pytest.mark.parametrize("bad", [
    {"type": "noul", "state": ["task", "content"], "question": "Is `content` buggy?", "true": "y", "false": "n"},
    {"type": "noul", "question": "Is this buggy?", "true": "y", "false": "n"},
    {"type": "noul", "question": "Is `content` buggy?", "true": "", "false": "n"},
    {"type": "choice", "question": "Which layer is `content`?", "options": {"only": "one"}},
    {"type": "pick", "state": ["task", "files"], "question": "Which of `files` for `task`?"},
    {"type": "noul", "state": ["files"], "question": "Are `files` ok?", "true": "y", "false": "n"},
])
def test_malformed_template_is_rejected_at_manifest_load(tmp_path, bad):
    repo = make_repo(tmp_path, FILES, questions={**TEMPLATES, "bad": bad})
    post = Recorder()
    out = scout.scout_files(repo, ["src/**"], ["known-issue"], post, budget())
    assert out["blocked"].startswith("template bad") and post.calls == []


def test_level8_build_questions_refuses_a_pick_template():
    questions, problem = ask.build_questions({"questions": TEMPLATES}, ["pick-first-for-task"])
    assert questions is None and "malformed" in problem


def test_repo_manifest_templates_load_with_the_default_state():
    data = json.loads((Path(__file__).parents[1] / ask.MANIFEST).read_text())
    assert all(manifest.template_problem(t, v) is None for t, v in data["questions"].items())


def test_ask_jev_makes_exactly_one_call_over_the_bundle(repo):
    post = Recorder()
    out = scout.ask_jev(repo, "p3", list(FILES), ["triage-bundle"], post, budget())
    assert len(post.calls) == 1 and post.calls[0]["state"] == {"task": PROMPTS["p3"], "files": FILES}
    assert out["outcome"] == "answered" and out["sha256"]["src/domain/billing.ts"] == sha(GOOD)


def test_ask_jev_refuses_21_paths(tmp_path):
    files = {f"f{i}.ts": f"const a{i} = {i};\n" for i in range(21)}
    repo = make_repo(tmp_path, files)
    post = Recorder()
    out = scout.ask_jev(repo, "p3", list(files), ["triage-bundle"], post, budget())
    assert out["outcome"] == "refused" and "1-20" in out["reason"] and post.calls == []


def test_ask_jev_refuses_an_aggregate_over_64000_bytes_with_part_sizes(tmp_path):
    files = {f"big{i}.ts": "x" * 25_000 + "\n" for i in range(3)}
    repo = make_repo(tmp_path, files)
    post = Recorder()
    out = scout.ask_jev(repo, "p3", list(files), ["triage-bundle"], post, budget())
    assert out["reason"] == "aggregate over 64,000 bytes" and post.calls == []
    assert out["sizes"]["total"] > 64_000 and set(out["sizes"]["files"]) == set(files)


def test_ask_jev_refuses_the_whole_bundle_when_one_file_changed(repo, tmp_path):
    (tmp_path / "src/http/routes.ts").write_text("changed\n")
    post = Recorder()
    out = scout.ask_jev(repo, "p3", list(FILES), ["triage-bundle"], post, budget())
    assert out["outcome"] == "refused" and "differs" in out["reason"] and post.calls == []


def test_approve_glob_and_prompt_file_print_but_never_write(repo, tmp_path, capsys):
    before = (tmp_path / ask.MANIFEST).read_bytes()
    (tmp_path / "prompt.txt").write_text(PROMPTS["p3"])
    assert cli.main(["approve", "--glob", "src/**", "--repo", repo]) == 0
    glob_out = json.loads(capsys.readouterr().out)
    assert cli.main(["approve", "--prompt-file", str(tmp_path / "prompt.txt"), "--id", "p3"]) == 0
    assert json.loads(capsys.readouterr().out) == {"prompts": {"p3": PROMPTS["p3"]}}
    assert glob_out["files"] == {p: sha(t) for p, t in FILES.items()}
    assert (tmp_path / ask.MANIFEST).read_bytes() == before


def test_approve_glob_lists_refused_files_with_reasons(tmp_path):
    repo = make_repo(tmp_path, {"a.ts": GOOD, ".env.local": "X=1\n", "k.ts": "-----BEGIN RSA PRIVATE KEY-----\n"})
    out = manifest.approve_glob(repo, "*")
    assert out == {"files": {"a.ts": sha(GOOD)}, "refused": {
        ".env.local": "denied path", "k.ts": "sensitive content", ask.MANIFEST: "the manifest itself"}}


@pytest.mark.parametrize("pattern, path, hit", [("src/**/*.ts", "src/a/b/c.ts", True), ("src/**/*.ts", "src/c.ts", True),
                                                ("src/*.ts", "src/a/c.ts", False), ("**", "x/y", True),
                                                ("tests/**/*.ts", "src/tests/a.ts", False), ("a?.ts", "ab.ts", True)])
def test_glob_semantics(pattern, path, hit):
    assert bool(manifest.glob_regex(pattern).match(path)) is hit
