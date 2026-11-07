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
    # Quoting and escaping are deleted by Bash, so they cannot hide HEAD.
    'git push origin H"E"AD',
    "git push origin 'HEAD'",
    "git push origin HE\\AD",
    'bash -c "git push origin HEAD"',
    "env X=1 git push origin HEAD",
    "git push origin +HEAD",
    "git push origin 'refs/heads/*'",
    "git push origin feature/x:",
    "git push origin -- HEAD",
    "git push origin feature/x\ngit push",
    # Codex round 2: a protected name split by quoting or escaping is still main.
    "git push origin m'a'in",
    'git push origin "ma""in"',
    "git push origin ma\\in",
    "git push origin HEAD:m'a'in",
    "git push origin refs/heads/m'a'in",
    "git push origin pr'od'",
    "git merge feature/x && git push origin m'a'in",
    # Separators and line breaks inside quotes or escapes are data, not command ends.
    'git push origin "x;" HEAD',
    "git push origin 'a|b' HEAD",
    "git push origin x\\;y HEAD",
    "git push origin ma\\\nin",
    "git push origin \\\nHEAD",
    # Wrappers that hand git a whole command string.
    "sh -c 'cd /tmp/x && git push'",
    'eval "git push origin HE""AD"',
    "bash -c \"bash -c 'git push origin HEAD'\"",
    # A global option that takes a separate value must not hide the push.
    "git --git-dir /tmp/x/.git push origin HEAD",
    "git --work-tree /tmp/x push",
    # Unbalanced quoting cannot be read, so it is refused.
    "git push origin 'HEAD",
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


# Round 3 (RA-8245): the value of a word is decided at run time, not by its text.
# Every case here was L1 or L2 at 571862e5; each one runs a push to HEAD or main.
@pytest.mark.parametrize("command", [
    "bash -c $'git push origin HEAD'",
    "eval $'git push origin HEAD'",
    "git $'\\x70ush' origin HEAD",
    "git pu''sh origin HEAD",
    'git pu"sh" origin HEAD',
    "git pu${x}sh origin HEAD",
    "p=push; git $p origin HEAD",
    "g=git; $g push origin HEAD",
    "printf 'gi%st pu%sh origin HEAD' t s | bash",
    "git -c alias.p=push p origin HEAD",
    "git send-pack origin HEAD",
    "git subtree push --prefix x origin main",
    "/usr/libexec/git-core/git-push origin HEAD",
    "python3 -c \"import subprocess; subprocess.run(['git','push','origin','HEAD'])\"",
    "node -e \"require('child_process').execSync('git push origin HEAD')\"",
])
def test_push_hidden_behind_a_run_time_value_is_l3(command: str) -> None:
    assert tier(command) == LADDER.TIER_IRREVERSIBLE, command


@pytest.mark.parametrize("command", [
    "git log $REF --oneline",
    "cd $HOME && ls",
    'git commit -m "fix the push check"',
    "rg -n push swarm/",
    "echo $PATH",
    "git diff origin/main...HEAD | head",
    "cat <<EOF\nit's fine\nEOF",
])
def test_ordinary_commands_with_values_or_the_word_push_stay_below_l3(command: str) -> None:
    assert tier(command) < LADDER.TIER_IRREVERSIBLE, command


# Round 4 (RA-8245): a command substitution runs before the command that hosts it, so
# an ordinary `git log` or `git commit` carried a push. Both gate consumers must deny.
_SUBSTITUTED_PUSHES = [
    "git log `git push origin HEAD`",
    "git commit -m `git push origin HEAD`",
    "git log `git push origin main`",
    "ls `git push`",
    "git status `echo x; git push origin HEAD`",
]


@pytest.mark.parametrize("command", _SUBSTITUTED_PUSHES)
def test_push_inside_a_command_substitution_is_l3(command: str) -> None:
    assert tier(command) == LADDER.TIER_IRREVERSIBLE, command


@pytest.mark.parametrize("command", _SUBSTITUTED_PUSHES)
def test_both_gate_consumers_deny_a_substituted_push(command: str) -> None:
    import app.server.tool_gate as tool_gate
    import swarm.nexus.autonomy_gate as autonomy_gate

    assert tool_gate.decide("Bash", {"command": command}).allow is False, command
    assert autonomy_gate.decide("Bash", {"command": command}) is not None, command


# Round 5 (RA-8245): code hides in a value Bash or git runs later, and data must stay data.
_DEFERRED_PUSHES = [
    "shopt -s expand_aliases\nalias g='git push origin HEAD'\ng",
    "alias g='git push origin HEAD'; g",
    "GIT_EDITOR='git push origin HEAD' git commit",
    "git -c core.editor='git push origin HEAD' commit",
    "git fetch --upload-pack='git push origin HEAD' origin",
    "gh alias set --shell p 'git push origin HEAD'",
    "trap 'git push origin HEAD' EXIT",
]


@pytest.mark.parametrize("command", _DEFERRED_PUSHES)
def test_push_in_a_value_that_runs_later_is_l3_in_both_consumers(command: str) -> None:
    import app.server.tool_gate as tool_gate
    import swarm.nexus.autonomy_gate as autonomy_gate

    assert tier(command) == LADDER.TIER_IRREVERSIBLE, command
    assert tool_gate.decide("Bash", {"command": command}).allow is False, command
    assert autonomy_gate.decide("Bash", {"command": command}) is not None, command


@pytest.mark.parametrize("command", [
    'echo "git push origin HEAD"',
    'printf %s "git push origin HEAD"',
    'git commit -m "git push origin HEAD"',
    'gh pr create --title x --body "run git push origin HEAD later"',
    'grep -rn "git push origin HEAD" docs/',
    "alias ll='ls -la'",
])
def test_quoted_push_text_is_data_not_an_action(command: str) -> None:
    import swarm.nexus.autonomy_gate as autonomy_gate

    assert tier(command) < LADDER.TIER_IRREVERSIBLE, command
    assert autonomy_gate.decide("Bash", {"command": command}) is None, command


@pytest.mark.parametrize("command", [
    "git log `date`",
    "git commit -m 'fix `foo` in bar'",
    "echo $((1+2))",
    "git log $(git rev-parse HEAD)",
])
def test_harmless_substitutions_stay_below_l3(command: str) -> None:
    assert tier(command) < LADDER.TIER_IRREVERSIBLE, command
