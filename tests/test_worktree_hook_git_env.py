"""RA-8375: only the folder the hook decided on may choose the repository its git reads and changes.

CodeRabbit on c40ebe7a: the hook's git calls inherited the caller's environment. With GIT_DIR naming this project's
main checkout, the commit check read the main checkout's HEAD, so a worktree holding a commit on no branch was
removed. With GIT_DIR naming another repository, create built a worktree of that repository inside this project. The
script now hands git no GIT_* variable at all, so the cases below include one that is on nobody's list of names.
"""
from pathlib import Path

import pytest
from test_worktree_hook import LOOSE, _command, _event, _git, _project, _run, _worktrees

INHERITED = {  # case -> the variables the hook inherits, given the folder that holds both repositories
    "git-dir-of-this-project": lambda root: {"GIT_DIR": str(root / "project" / ".git")},
    "git-dir-of-another-repository": lambda root: {"GIT_DIR": str(root / "other" / ".git")},
    "git-dir-and-work-tree-of-another-repository": lambda root: {"GIT_DIR": str(root / "other" / ".git"),
                                                                 "GIT_WORK_TREE": str(root / "other")},
    "common-dir-of-another-repository": lambda root: {"GIT_COMMON_DIR": str(root / "other" / ".git")},
    "a-variable-on-no-list": lambda root: {"GIT_CONFIG_COUNT": "not a number"},  # git itself stops on this one
}


def _hook(project: Path, event: str, inherited: dict[str, str], **fields: object):
    return _run(_command(event), project, _event(event, **fields), inherited=inherited)


@pytest.mark.parametrize("case", INHERITED)
def test_a_git_variable_the_hook_inherits_cannot_choose_the_repository(tmp_path: Path, case: str) -> None:
    project, other = _project(tmp_path), _project(tmp_path, "other", install=False)
    parked = Path(_hook(project, "WorktreeCreate", {}, name="parked").stdout.strip())
    assert all(_git(project, parked, *step).returncode == 0 for step in LOOSE)  # a commit on no branch
    inherited = INHERITED[case](tmp_path)

    kept = _hook(project, "WorktreeRemove", inherited, worktree_path=str(parked))
    assert kept.returncode == 1 and "on no branch" in kept.stderr, (kept.stdout, kept.stderr)
    assert parked.is_dir() and _worktrees(project) == 2

    second = project / ".claude" / "worktrees" / "second"
    made = _hook(project, "WorktreeCreate", inherited, name="second")
    assert made.returncode == 0 and made.stdout.splitlines() == [str(second)], made.stderr
    assert _worktrees(project) == 3 and _worktrees(other) == 1  # a worktree of this project, none of the other

    gone = _hook(project, "WorktreeRemove", inherited, worktree_path=str(second))
    assert gone.returncode == 0 and not second.exists() and _worktrees(project) == 2, gone.stderr
