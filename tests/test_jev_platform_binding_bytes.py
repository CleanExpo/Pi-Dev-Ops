"""Round 16 P1s on the AAA binding: AAA means the exact bytes verified are the bytes committed at the named commit.

P1-AAA-INDEX-FLAGS-BYPASS: `git diff --quiet HEAD` reads through the index, so assume-unchanged or skip-worktree hid an
edited record and it kept AAA. P1-VERIFY-RECEIPT-GIT-ENV-REDIRECTION: the receipt's commit id came from plain
`git rev-parse` and followed an inherited GIT_DIR. Each test first proves the bypass is live for plain git (positive
control). Offline, temp repos.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import test_jev_platform_committed_inputs as ci
from jev_scale_support import git
from test_jev_platform_committed_inputs import budget, recording

from jev_platform import __main__ as cli
from jev_platform import engine

repo = ci.repo  # a temp repo standing in for engine.ROOT


def committed_records(root) -> None:
    engine.calibrate(ci.RULE, recording([]), budget())
    git(root, "add", "-f", "records")
    git(root, "commit", "-qm", "records")
    assert engine.artifact_rating(ci.RULE) == ("AAA", [])  # positive control: bound as committed


def reformat_record(path) -> None:  # still verifies: same JSON, different bytes
    path.write_text(json.dumps(json.loads(path.read_text()), indent=3) + "\n")


def pad_scored(path) -> None:  # still verifies: blank lines are skipped
    path.write_text(path.read_text() + "\n")


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
@pytest.mark.parametrize("name, edit", [(f"{ci.RULE}.json", reformat_record), (f"{ci.RULE}.scored.jsonl", pad_scored)])
def test_an_index_flag_does_not_hide_an_edited_record(repo, flag, name, edit):
    committed_records(repo)
    path = engine.RECORDS / name
    git(repo, "update-index", flag, str(path.relative_to(repo)))
    edit(path)
    assert subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD"]).returncode == 0  # control: hidden
    assert engine.artifact_rating(ci.RULE) == ("AA", ["not bound to HEAD"])


def test_the_receipt_names_roots_commit_under_an_inherited_git_dir(repo, tmp_path_factory, monkeypatch, capsys):
    committed_records(repo)
    head = git_head(repo)
    other = tmp_path_factory.mktemp("x") / "other"
    shutil.copytree(repo, other)
    git(other, "commit", "--allow-empty", "-qm", "another commit")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert git_head(repo) == git_head(other) != head  # control: plain git follows GIT_DIR
    assert cli.main(["verify-calibration", "--rule", ci.RULE]) == 0
    assert capsys.readouterr().out == f"{ci.RULE}: AAA @ {head}\n"


def git_head(root) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
