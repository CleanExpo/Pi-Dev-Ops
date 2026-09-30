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
from jev_platform import committed as verified
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


def committed_alternative(root):
    """Round 17: a second valid calibration pair committed at alt/, whose bytes differ from HEAD's records/."""
    committed_records(root)
    alt = root / "alt"
    shutil.copytree(engine.RECORDS, alt)
    reformat_record(alt / f"{ci.RULE}.json")
    pad_scored(alt / f"{ci.RULE}.scored.jsonl")
    git(root, "add", "-f", "alt")
    git(root, "commit", "-qm", "alt")
    return alt


def swap_files(root, alt) -> None:
    for name in (f"{ci.RULE}.json", f"{ci.RULE}.scored.jsonl"):
        (engine.RECORDS / name).unlink()
        (engine.RECORDS / name).symlink_to(alt / name)


def swap_directory(root, alt) -> None:
    shutil.rmtree(engine.RECORDS)
    engine.RECORDS.symlink_to(alt, target_is_directory=True)


@pytest.mark.parametrize("swap", [swap_files, swap_directory])
def test_a_symlink_does_not_choose_the_committed_path_compared(repo, swap):
    """Round 17 P1-AAA-SYMLINK-PATH-SUBSTITUTION: bytes read through a symlink are compared at the records' own path."""
    alt = committed_alternative(repo)
    swap(repo, alt)
    rel = (engine.RECORDS / f"{ci.RULE}.json").relative_to(repo)
    at_head = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{rel.as_posix()}"], capture_output=True).stdout
    assert (engine.RECORDS / f"{ci.RULE}.json").read_bytes() != at_head  # control: the bytes checked are not HEAD's
    assert engine.artifact_rating(ci.RULE) == ("AA", ["not bound to HEAD"])


def test_a_symlink_to_identical_untracked_bytes_is_still_not_aaa(repo):
    """Round 17: the refusal is of the symlink itself, as committed.file_at_head does (round 13)."""
    committed_records(repo)
    copy = repo / "copy"
    shutil.move(engine.RECORDS, copy)
    engine.RECORDS.symlink_to(copy, target_is_directory=True)
    assert engine.load_record(ci.RULE) is not None  # control: the same bytes are readable through the link
    assert engine.artifact_rating(ci.RULE) == ("AA", ["not bound to HEAD"])


def test_lineage_is_checked_against_the_commit_the_receipt_names(repo, monkeypatch):
    """Round 18 P1-AAA-LINEAGE-HEAD-SNAPSHOT: HEAD moving between the binding and the lineage check must not admit
    an eval_sha outside the history of the commit the receipt names."""
    committed_records(repo)
    descends = git_head(repo)  # its history holds the record's eval_sha
    tree = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True).stdout
    root = subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit-tree",
                           tree.strip(), "-m", "same files, no history"], capture_output=True, text=True).stdout.strip()
    git(repo, "reset", "-q", "--soft", root)
    assert engine.artifact_rating(ci.RULE) == ("FAIL", ["eval_sha is not in the history of HEAD"])  # control: stable
    seen = []

    def moving_head(repo_, rev="HEAD", env=None):  # HEAD moves to `descends` after the first resolution
        seen.append(rev)
        return root if len(seen) == 1 else descends
    monkeypatch.setattr(verified, "resolve", moving_head)
    assert engine.artifact_rating(ci.RULE) == ("FAIL", ["eval_sha is not in the history of HEAD"])


def git_head(root) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
