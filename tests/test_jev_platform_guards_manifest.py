"""Guard sweep 29/09: one offline control per jev_platform.manifest guard that no test used to reach.

Each test fails with its guard removed (tests/mutation/jev_platform_mutants.py) and every refusal asserts
ZERO requests. No network, no keys: `post` is a recording fake.
"""
from __future__ import annotations

import os

import pytest
from jev_scale_support import GOOD, TEMPLATES, Recorder, budget, make_repo, sha

from jev_platform import ask, manifest, scout

FILES = {"src/domain/billing.ts": GOOD}


def scout_known_issue(repo, post):
    return scout.scout_files(repo, ["src/**"], ["known-issue"], post, budget())


BAD = {
    "choice-blank-option": {"type": "choice", "question": "Which layer is `content`?",
                            "options": {"a": "HTTP routing", "b": "  "}},
    "pick-without-state": {"type": "pick", "question": "Which part of `content` matters?", "none": "nothing"},
    "unknown-type": {"type": "essay", "question": "Describe `content`.", "true": "y", "false": "n"},
    "no-question": {"type": "noul", "true": "y", "false": "n"},
    "question-not-text": {"type": "noul", "question": ["`content`"], "true": "y", "false": "n"},
    "state-object": {"type": "noul", "state": {"task": 1, "content": 2},
                     "question": "Is `content` relevant to `task`?", "true": "y", "false": "n"},
}


@pytest.mark.parametrize("tid", sorted(BAD))
def test_malformed_template_blocks_the_whole_manifest_before_any_request(tmp_path, tid):
    """Guard sweep 29/09: blank option, pick without [task, files], unknown type, missing question text and a
    non-list state are each refused at load, even when only a valid template is selected."""
    repo = make_repo(tmp_path, FILES, questions={**TEMPLATES, tid: BAD[tid]})
    post = Recorder()
    out = scout_known_issue(repo, post)
    assert out["blocked"].startswith(f"template {tid}") and post.calls == []


def test_the_unmodified_fixture_sends_one_request(tmp_path):
    """Guard sweep 29/09 positive control: without the bad template the same call is answered."""
    post = Recorder()
    out = scout_known_issue(make_repo(tmp_path, FILES), post)
    assert "blocked" not in out and len(post.calls) == 1


def test_pick_question_over_the_character_cap_is_refused_before_any_request(tmp_path):
    """Guard sweep 29/09: a pick template's question has no other length check on the pick_first path."""
    long_pick = {"type": "pick", "state": ["task", "files"], "none": "No listed file fits",
                 "question": "Which one of `files` should be opened first to work on `task`? " + "Be exact. " * 150}
    assert len(long_pick["question"]) > ask.MAX_TEMPLATE_CHARS
    repo = make_repo(tmp_path, FILES, questions={**TEMPLATES, "long-pick": long_pick})
    post = Recorder()
    out = scout.pick_first(repo, "p3", "long-pick", list(FILES), post, budget())
    assert out == {"outcome": "refused", "reason": f"template long-pick: question over {ask.MAX_TEMPLATE_CHARS} "
                                                   "characters"} and post.calls == []


@pytest.mark.parametrize("prompts", [[], ["p3"], {"p3": 5}, {"p3": "  "}, {"p3": ""}])
def test_malformed_prompts_block_the_manifest_before_any_request(tmp_path, prompts):
    """Guard sweep 29/09: prompts must be an object of non-blank texts, even for a run that takes no prompt."""
    repo = make_repo(tmp_path, FILES, prompts=prompts)
    post = Recorder()
    out = scout_known_issue(repo, post)
    assert out["blocked"] == "prompts must map ids to non-empty text" and post.calls == []


def test_approve_glob_refuses_a_tracked_path_naming_a_banned_publisher(tmp_path):
    """Guard sweep 29/09: `docs/iicrc.md` is not on the name deny-list, only the sensitive-path screen stops it."""
    repo = make_repo(tmp_path, {"docs/iicrc.md": "plain notes\n", "docs/ok.md": "plain notes\n"})
    out = manifest.approve_glob(repo, "docs/*")
    assert out["refused"] == {"docs/iicrc.md": "denied path"} and out["files"] == {"docs/ok.md": sha("plain notes\n")}


def test_approve_glob_refuses_a_tracked_symlink_as_unreadable(tmp_path):
    """Guard sweep 29/09: read_confined's O_NOFOLLOW error is reported per file, never raised."""
    (tmp_path / "src").mkdir()
    os.symlink("real.ts", tmp_path / "src" / "link.ts")
    repo = make_repo(tmp_path, {"src/real.ts": GOOD})
    out = manifest.approve_glob(repo, "src/*")
    assert out["refused"] == {"src/link.ts": "unreadable: OSError"} and out["files"] == {"src/real.ts": sha(GOOD)}


def test_approve_glob_refuses_a_tracked_file_over_the_cap(tmp_path):
    """Guard sweep 29/09: a 40,000-byte tracked file is listed as refused, never given a digest."""
    repo = make_repo(tmp_path, {"src/big.txt": "z" * 40_000, "src/ok.ts": GOOD})
    out = manifest.approve_glob(repo, "src/*")
    assert out["refused"] == {"src/big.txt": "file over 32,000 bytes"} and out["files"] == {"src/ok.ts": sha(GOOD)}


@pytest.mark.parametrize("text", ["", "   \n\n", "Fix the drying plan to match IICRC S500.\n",
                                  "Quote Standards Australia on this.\n"])
def test_approve_prompt_refuses_empty_or_sensitive_text(tmp_path, text):
    """Guard sweep 29/09: an empty/blank prompt file, or one naming a banned publisher, yields no prompts entry."""
    path = tmp_path / "prompt.txt"
    path.write_text(text)
    assert manifest.approve_prompt(str(path), "p9") == {"refused": {"p9": "empty or sensitive prompt text"}}


def test_approve_prompt_accepts_plain_text(tmp_path):
    """Guard sweep 29/09 positive control for the refusals above."""
    path = tmp_path / "prompt.txt"
    text = "Find the file that rounds prorated amounts.\n"
    path.write_text(text)
    assert manifest.approve_prompt(str(path), "p9") == {"prompts": {"p9": text}}
