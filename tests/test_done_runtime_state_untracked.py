"""Done-harness runtime state must never be tracked (RA-7559).

donectl rewrites three kinds of file under .claude/done on every run:
  ACTIVE.json              one shared map of branch/worktree -> work item
  work/<id>/state.json     verification results, rewritten by every `verify`
  work/<id>/notes.jsonl    appended by `note`
When they were tracked, every PR committed its own copy of ACTIVE.json. On
2026-11-06 merging #980 left #973, #977, #978 and #979 all CONFLICTING, each on
.claude/done/ACTIVE.json alone. Tracked state.json also dirtied the tree on every
`verify`, so the release gate could not mint a receipt (RA-7559).

contract.json and lock.json stay tracked: they are the locked finish line and its
binding, written once, and are the review evidence.

The check reads the tree (git ls-files), not the PR diff: it needs no base ref,
and it also fails a stale branch that still carries the files.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DONE_PREFIX = ".claude/done/"
RUNTIME_NAMES = ("ACTIVE.json", "state.json", "notes.jsonl")
_RUNTIME = re.compile(r"(?:^|/)(?:ACTIVE\.json|state\.json|notes\.jsonl)$")


def tracked_runtime_files(tracked_paths: list[str]) -> list[str]:
    """Return the tracked paths under .claude/done that are donectl runtime state."""
    return sorted(
        p for p in tracked_paths if p.startswith(DONE_PREFIX) and _RUNTIME.search(p)
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _ls_files(cwd: Path) -> list[str]:
    return [line for line in _git(cwd, "ls-files").splitlines() if line]


def test_no_done_runtime_state_is_tracked() -> None:
    hits = tracked_runtime_files(_ls_files(REPO))
    assert not hits, (
        "donectl runtime state is tracked; it is per-worktree and causes merge "
        "conflicts across PRs (RA-7559). Untrack it with "
        "`git rm --cached <path>` (the file stays on disk, ignored):\n  "
        + "\n  ".join(hits)
    )


def test_gitignore_covers_runtime_state_but_not_evidence() -> None:
    def ignored(path: str) -> bool:
        return (
            subprocess.run(
                ["git", "check-ignore", "-q", "--no-index", path], cwd=REPO
            ).returncode
            == 0
        )

    assert ignored(".claude/done/ACTIVE.json")
    assert ignored(".claude/done/work/w_example/state.json")
    assert ignored(".claude/done/work/w_example/notes.jsonl")
    assert not ignored(".claude/done/work/w_example/contract.json")
    assert not ignored(".claude/done/work/w_example/lock.json")


def test_detector_fires_on_planted_runtime_file(tmp_path: Path) -> None:
    """Mutation control: a repo that tracks the runtime files is caught."""
    _git(tmp_path, "init", "-q")
    planted = [
        ".claude/done/ACTIVE.json",
        ".claude/done/work/w_1/state.json",
        ".claude/done/work/w_1/notes.jsonl",
    ]
    kept = [
        ".claude/done/work/w_1/contract.json",
        ".claude/done/work/w_1/lock.json",
        "app/state.json",  # outside .claude/done: not the harness's file
    ]
    for rel in planted + kept:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}\n")
    _git(tmp_path, "add", "-A")
    assert tracked_runtime_files(_ls_files(tmp_path)) == sorted(planted)

    _git(tmp_path, "rm", "-q", "--cached", *planted)
    assert tracked_runtime_files(_ls_files(tmp_path)) == []
