"""RA-7386 — git global options must not move a command out from under a rule.

Every git rule in ``autonomy_ladder`` anchors on ``git <subcommand>``. Git accepts
global options in between, so ``git -C /repo reset --hard`` reached none of the
work-discard rules #682 added, nor the pre-existing ``git-force-push`` rule, and
``git -C . push origin main`` classified L1 instead of L3. Two gate surfaces, one
root cause; this file covers both.

**Why the fix cannot regress the corpus.** Matching is ``original OR normalised``,
never normalised alone, so the rewrite can only ever ADD a match. That is a
property of the construction rather than of the cases below — which matters,
because four rule designs on this file have leaked and every one of them passed
its own author's corpus. The must-allow half is still the load-bearing half:
over-denial is the safe direction for the SDK denylist but it costs the loop
ordinary git, and `git -C` is how a coding agent works in a sibling worktree.

**Normalisation is applied only where a hit RAISES the tier** — ``L3_BASH_RE``
and ``L2_BASH``, never ``READ_ONLY_BASH``, where it would let ``git -C . status``
fall L1 -> L0. ``test_read_only_is_not_normalised`` pins that.
"""
from __future__ import annotations

import time

import pytest

from app.server.tool_gate import decide
from swarm.nexus.autonomy_ladder import (
    TIER_IRREVERSIBLE,
    TIER_LOCAL,
    classify,
    strip_git_global_opts,
)


def is_denied(command: str) -> bool:
    """Run a Bash command past the real unattended-loop gate."""
    return not decide("Bash", {"command": command}).allow


def deny_label(command: str) -> str:
    return decide("Bash", {"command": command}).label


def tier(command: str) -> int:
    return classify("Bash", {"command": command})


# Every option form git accepts before a subcommand. `-C` is the one CodeRabbit
# reported; the rest are the same hole reached through git's documented surface.
OPTION_PREFIXES = [
    "-C .",
    "-C /repo",
    "-C ../sibling-worktree",
    "-c core.editor=true",
    "-c user.name=x",
    "--git-dir=/tmp/x/.git",
    "--work-tree=.",
    "--namespace=n",
    "--exec-path=/usr/lib/git-core",
    "--no-pager",
    "--paginate",
    "--no-optional-locks",
    "--literal-pathspecs",
    "-p",
    "-P",
    "-C . -c core.editor=true",          # stacked
    "--no-pager -C /repo --work-tree=.",  # stacked, mixed
]

# One representative destroying spelling per work-discard family, plus the
# pre-existing force-push rule that has always had the same hole.
DESTRUCTIVE_TAILS = [
    "reset --hard",
    "reset --merge",
    "checkout -- .",
    "checkout HEAD src/app.py",
    "checkout -f main",
    "restore .",
    "clean -fdx",
    "stash drop",
    "stash clear",
    "push --force origin main",
]


@pytest.mark.parametrize("prefix", OPTION_PREFIXES)
@pytest.mark.parametrize("tail", DESTRUCTIVE_TAILS)
def test_global_options_do_not_bypass_the_sdk_denylist(prefix, tail):
    """The whole grid: every option form x every destroying subcommand."""
    command = f"git {prefix} {tail}"
    assert is_denied(command), f"global-option bypass: {command}"


@pytest.mark.parametrize("command", [
    # The exact case in the review comment.
    "git -C . reset --hard",
    # `--git-dir=.git` denied before this fix only by accident, because
    # `\\bgit\\s+reset\\b` matched the `.git reset` substring. A path that does
    # not end in `.git` showed the rule was never really covering it.
    "git --git-dir=/tmp/elsewhere reset --hard",
    # Separated-value spellings of the value-bearing long options.
    "git --work-tree . reset --hard",
    "git --git-dir /tmp/x/.git clean -fdx",
])
def test_the_reported_and_adjacent_spellings_are_denied(command):
    assert is_denied(command), f"still bypassing: {command}"


# --- The L3 half: nobody reported this, measurement found it ---------------

@pytest.mark.parametrize("protected", ["main", "master", "prod", "production"])
@pytest.mark.parametrize("prefix", ["-C .", "-c core.editor=true", "--no-pager"])
def test_push_to_a_protected_ref_stays_l3_behind_global_options(prefix, protected):
    """`git -C . push origin main` fell L3 -> L1, so the CLI hook passed it."""
    command = f"git {prefix} push origin {protected}"
    assert tier(command) == TIER_IRREVERSIBLE, f"L3 leak: {command}"


@pytest.mark.parametrize("command", [
    "git -C . merge main",
    "git -C /repo merge feature/x",
    "git --no-pager merge main",
    "git -c core.editor=true merge main",
])
def test_merge_stays_l3_behind_global_options(command):
    assert tier(command) == TIER_IRREVERSIBLE, f"L3 leak: {command}"


# --- Must allow: this is the half that costs capability if it is wrong -----

@pytest.mark.parametrize("prefix", OPTION_PREFIXES)
@pytest.mark.parametrize("tail", [
    "status",
    "log --oneline",
    "diff",
    "diff -- src/app.py",
    "show HEAD",
    "add -A",
    "add -- src/app.py",
    "commit -m 'fix: thing'",
    "checkout main",
    "checkout -b feature/x",
    "checkout -B feature/x origin/main",
    "switch -c feature/x",
    "restore --staged .",
    "clean -n",
    "clean --dry-run -d",
    "stash",
    "stash pop",
    "stash list",
    "reset --soft HEAD~1",
    "reset --keep HEAD~1",
    "rev-parse HEAD",
    "fetch origin main",
])
def test_ordinary_git_behind_global_options_is_still_allowed(prefix, tail):
    """Working in a sibling worktree with `-C` is how a coding agent operates."""
    command = f"git {prefix} {tail}"
    assert not is_denied(command), (
        f"ordinary command wrongly denied as {deny_label(command)!r}: {command}"
    )


def test_read_only_is_not_normalised():
    """`git -C . status` must stay L1, not fall to L0.

    READ_ONLY_BASH is the one pattern whose hit LOWERS the tier, so normalising
    for it would turn this fix's raise into a drop. Plain `git status` is L0 by
    its `^`-anchored rule and stays that way.
    """
    assert tier("git -C . status") == TIER_LOCAL
    assert tier("git -C . log") == TIER_LOCAL
    assert tier("git status") < TIER_LOCAL


# --- Invariants this change must not disturb -------------------------------

def test_git_rm_skip_is_unchanged_in_both_directions():
    """The `git rm` segment skip is pre-existing and NOT this change's to fix.

    `git rm -rf .` is allowed today because `_inspect_bash` skips any segment
    beginning `git rm`. `git -C . rm -rf .` is denied today because the skip
    does not match it and `rm-rf` catches it. Normalising the second one alone
    would hand it the skip and silently UN-deny it — which is why the skip is
    applied per form. Both behaviours are pinned here so a later edit that
    changes either has to say so.
    """
    assert not is_denied("git rm -rf ."), "pre-existing `git rm` skip changed"
    assert is_denied("git -C . rm -rf ."), "normalisation un-denied a command"


def test_positive_control_the_gate_can_still_deny_and_allow():
    """A corpus of all-denied means nothing if the harness denies everything."""
    assert is_denied("rm -rf /tmp/whatever"), "gate no longer denies rm -rf"
    assert not is_denied("echo hello"), "gate denies a plainly benign command"


@pytest.mark.parametrize("command", [
    "git reset --hard",
    "git clean -fdx",
    "git stash drop",
    "git push --force origin main",
    "rm -rf /tmp/x",
    "terraform destroy",
    "DROP TABLE users",
])
def test_direct_spellings_are_still_denied(command):
    """The un-prefixed forms must be untouched by the rewrite."""
    assert is_denied(command), f"regression on a direct spelling: {command}"


# --- The normaliser itself -------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("git -C . reset --hard", "git reset --hard"),
    ("git -C /repo status", "git status"),
    ("git -c a.b=c reset --hard", "git reset --hard"),
    ("git --work-tree=. clean -fdx", "git clean -fdx"),
    ("git --git-dir /tmp/x status", "git status"),
    ("git --no-pager -C . stash drop", "git stash drop"),
    ("git -p log", "git log"),
    # Nothing to strip: unchanged, including the subcommand's own `-p`/`-C`.
    ("git status", "git status"),
    ("git log -p", "git log -p"),
    ("git checkout -- .", "git checkout -- ."),
    ("", ""),
    ("echo hello", "echo hello"),
    # Two calls in one string are each normalised.
    ("git -C a status && git -C b reset --hard",
     "git status && git reset --hard"),
])
def test_strip_git_global_opts(raw, expected):
    assert strip_git_global_opts(raw) == expected


def test_stacking_past_any_fixed_cap_still_normalises():
    """A fixed iteration cap would be a bypass one option past it.

    `git -C x -C y ...` is valid git — the paths compose. The loop is bounded by
    input length instead, so there is no count at which stripping gives up.
    """
    command = "git " + ("-C . " * 500) + "reset --hard"
    assert strip_git_global_opts(command) == "git reset --hard"
    assert is_denied(command), "stacked global options bypassed the gate"


@pytest.mark.parametrize("hostile", [
    "git " + ("-C . " * 2000) + "reset --hard",
    "git " + ("-c a.b=c " * 2000) + "status",
    "git " + ("--no-pager " * 2000) + "status",
    "git " + ("-" * 4000) + " status",
    "git -C " + ("../" * 4000) + " status",
    ("git -C . " * 1000) + "status",
])
def test_matching_is_not_catastrophically_backtracking(hostile):
    """These run in a PreToolUse hook, so a hang is its own denial of service."""
    started = time.monotonic()
    decide("Bash", {"command": hostile})
    classify("Bash", {"command": hostile})
    assert time.monotonic() - started < 1.0, "normalisation backtracks badly"


# --- Known boundaries, recorded rather than implied ------------------------

def test_alias_smuggling_is_a_documented_boundary():
    """`git -c alias.z='reset --hard' z` is NOT closed by this change.

    Prefix-stripping cannot catch it: the destructive verb lives inside an
    option *value*, not after the subcommand. Tracked separately rather than
    left to look like coverage. This test documents the gap; when it is fixed,
    it should flip to an assertion that the command is denied.
    """
    assert not is_denied("git -c alias.z='reset --hard' z")
