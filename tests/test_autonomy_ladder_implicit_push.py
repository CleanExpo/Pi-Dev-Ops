"""RA-8245 — a push whose destination is not written on the line is L3.

The push rules saw a protected branch only when it was SPELLED: `main`, `master`,
`prod`, `production`. A push that names no destination, or names it through an
indirection, writes whatever branch is checked out — possibly main — and scored
L2. Codex found it on the gate-local-merge review: on a `main` checkout,
`git merge feature/x && git push origin HEAD` landed on main with no stop. The
removed local-merge rule had only hidden it for that one chain;
`git commit -m x && git push origin HEAD` was already open.

Resolving the checked-out branch at hook time cannot close this: the same command
can switch branch first (`git checkout main && git push origin HEAD`). So the
rule is textual and fails closed: unless every destination of every `git push`
is a plain literal branch name on the line, the command is L3. An agent pushes a
feature branch by naming it: `git push -u origin feature/x`.

The same rule closes RA-7409: `--all` and `--mirror` write every ref, naming none.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LADDER = _load("autonomy_ladder_implicit_push", "swarm/nexus/autonomy_ladder.py")


def tier(command: str) -> int:
    return LADDER.classify("Bash", {"command": command})


@pytest.mark.parametrize("command", [
    "git push",
    "git push origin",
    "git push -u origin HEAD",
    "git push origin HEAD",
    "git push origin @",
    "git push --set-upstream origin HEAD",
    "git push origin feature/x HEAD",
    "git push origin $BRANCH",
    'git push origin "$(git branch --show-current)"',
    "git push origin `git branch --show-current`",
    "git push -o ci.skip origin feature/x",
    "git push --all origin",
    "git push --mirror origin",
    "git push origin --tags",
    "git -C /tmp/x push origin HEAD",
    "git -c push.default=current push",
    # The chains Codex reproduced, and the commit form that was open before.
    "git merge feature/x && git push origin HEAD",
    "git merge --no-ff feature/x && git push",
    "git commit -m x && git push origin HEAD",
    "git checkout main && git push origin HEAD",
    "git push origin feature/x && git push origin HEAD",
])
def test_push_with_implicit_destination_is_l3(command: str) -> None:
    assert tier(command) == LADDER.TIER_IRREVERSIBLE, command


@pytest.mark.parametrize("command", [
    "git push origin feature/x",
    "git push -u origin feature/x",
    "git push --force-with-lease origin fix/gate-local-merge-not-l3",
    "git push origin HEAD:refs/heads/claude/my-feature",
    "git push origin HEAD:feature/x",
    "git merge origin/main && git push -u origin feature/x",
])
def test_push_naming_a_feature_branch_stays_outward_not_l3(command: str) -> None:
    assert tier(command) == LADDER.TIER_OUTWARD, command


@pytest.mark.parametrize("command", [
    "git merge origin/main",
    "git merge --no-ff --no-commit origin/main",
    "git log --oneline origin/main..HEAD",
    "git rev-parse HEAD",
])
def test_non_push_commands_are_unaffected(command: str) -> None:
    assert tier(command) < LADDER.TIER_OUTWARD, command
