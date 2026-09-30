"""Round 15 P1 (P1-COMMITTED-ROOT-GIT-ENV-REDIRECTION): an inherited GIT_* variable must not choose the repository.

`git -C root` still honours an inherited GIT_DIR, so every reader would have served another repository's committed
bytes as root's. Each test points GIT_DIR at a second repository holding a marker, proves the redirection is live for
plain git (positive control), then proves the readers still return root's committed content. The fix drops every
GIT_* variable, not only GIT_DIR (the unit test below). GIT_COMMON_DIR and GIT_OBJECT_DIRECTORY were probed on git 2.53
and did not change what `git -C root rev-parse HEAD` names, so they have no live control here. Offline, temp repos.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import test_jev_platform_committed_inputs as ci
from jev_scale_support import git
from test_jev_platform_committed_inputs import MARKER, budget, recording, run_recording
from test_jev_platform_git_integrity import REL_QUESTIONS, marker_registry

from jev_platform import committed, engine

repo, eval_repo = ci.repo, ci.eval_repo  # temp repos standing in for engine.ROOT and the eval harness


def other_repo(root, rel: str, text: str, where) -> str:
    """A second repository: a copy of `root` with `text` committed at `rel`. Returns its .git path."""
    other = where / "other"
    shutil.copytree(root, other)
    (other / rel).write_text(text)
    git(other, "commit", "-qam", "unreviewed")
    return str(other / ".git")


def plain_show(root, rev_path: str) -> str:
    """What git itself serves from `root` with the ambient environment: the positive control."""
    return subprocess.run(["git", "-C", str(root), "show", rev_path], capture_output=True, text=True).stdout


def test_decide_sends_roots_registry_with_another_git_dir_inherited(repo, tmp_path_factory, monkeypatch):
    other = other_repo(repo, REL_QUESTIONS, marker_registry(repo), tmp_path_factory.mktemp("x"))
    monkeypatch.setenv("GIT_DIR", other)
    assert MARKER in plain_show(repo, f"HEAD:{REL_QUESTIONS}")  # positive control: plain git is redirected
    sent = []
    engine.decide("The agent writes 'all tests passed' but no test ran.", [ci.RULE], 1, recording(sent), budget(0.5))
    assert len(sent) == 1 and MARKER not in json.dumps(sent)


def test_harness_reads_roots_questions_with_another_git_dir_inherited(eval_repo, tmp_path_factory, monkeypatch):
    questions = json.loads((eval_repo / "questions.json").read_text())
    questions["questions"][0]["question"] = MARKER
    other = other_repo(eval_repo, "questions.json", json.dumps(questions), tmp_path_factory.mktemp("x"))
    monkeypatch.setenv("GIT_DIR", other)
    assert MARKER in plain_show(eval_repo, "HEAD:questions.json")
    sent = []
    run_recording(sent)
    assert len(sent) == 1000 and not any(MARKER in json.dumps(b) for b in sent)


def test_a_supplied_env_cannot_redirect_the_readers_either(repo, tmp_path_factory):
    """A caller-supplied env is sanitised too: generate.py passes one, and a future caller might copy os.environ."""
    reviewed = (repo / REL_QUESTIONS).read_bytes()
    other = other_repo(repo, REL_QUESTIONS, marker_registry(repo), tmp_path_factory.mktemp("x"))
    env = {"PATH": os.environ["PATH"], "GIT_DIR": other}
    head = committed.resolve(repo)
    assert committed.resolve(repo, env=env) == head
    assert committed.at_head(repo, REL_QUESTIONS, env=env)[2] == reviewed
    assert committed.file_at_head(repo, repo / REL_QUESTIONS, env=env) == reviewed
    assert committed.blob(repo, committed.read(repo, REL_QUESTIONS, head)[0], env=env) == reviewed
    assert committed.is_ancestor(repo, head, head, env=env)


def test_the_sanitised_env_drops_every_git_variable_and_keeps_the_rest():
    env = committed.git_env({"PATH": "/p", "HOME": "/h", "GIT_DIR": "/x", "GIT_COMMON_DIR": "/y",
                             "GIT_OBJECT_DIRECTORY": "/z", "GIT_CONFIG_PARAMETERS": "'a.b'='c'",
                             "GIT_CONFIG_NOSYSTEM": "0"})
    assert env == {"PATH": "/p", "HOME": "/h", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def test_the_aaa_binding_check_is_not_redirected(repo, tmp_path_factory, monkeypatch):
    """engine.artifact_rating's ls-files/diff check runs git too: another repository must not bind a record to HEAD."""
    engine.calibrate(ci.RULE, recording([]), budget())
    git(repo, "add", "-f", "records")
    git(repo, "commit", "-qm", "records")
    assert engine.artifact_rating(ci.RULE) == ("AAA", [])  # positive control: bound as committed
    path = engine.RECORDS / f"{ci.RULE}.json"
    path.write_text(json.dumps(json.loads(path.read_text()), indent=3) + "\n")  # edited after commit: honest AA
    assert engine.artifact_rating(ci.RULE) == ("AA", ["not bound to HEAD"])
    other = tmp_path_factory.mktemp("x") / "other"
    shutil.copytree(repo, other)
    git(other, "commit", "-qam", "edited record, committed elsewhere")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD"]).returncode == 0  # control: live
    assert engine.artifact_rating(ci.RULE) == ("AA", ["not bound to HEAD"])
