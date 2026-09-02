"""RA-7387 — `git -c alias.X='<verb>' X` must not smuggle a verb past the gate.

Git runs an alias defined inline, so the destructive word sits inside an option
VALUE where `autonomy_ladder.strip_git_global_opts` cannot reach it:

    strip_git_global_opts("git -c alias.z='reset --hard' z") -> "git --hard' z"

This was a LIVE bypass, not a theoretical one. `.claude/settings.json` wires a
PreToolUse hook to `autonomy_gate.decide` -> `autonomy_ladder.classify`, and
classify scored the alias form tier 1 against tier 3 for the direct form — so an
unattended session could self-authorize an L3 force-push, hard reset or
`clean -fdx`.

TWO GATES, TWO RULE TABLES, AND THAT IS THE POINT OF THIS FILE.

  * `is_denied()` runs `app.server.tool_gate`, gated by `TAO_TOOL_GATE`
    (default "0"), so it is NOT enforcing in production. It reads SEGMENT_RULES.
  * `tier()` runs `classify`, which the always-on hook consumes. It reads
    `L3_BASH_RE` in `swarm/nexus/autonomy_rules.py`.

A fix to one leaves the other open, and a test through one cannot see the other.
Found the hard way: a sabotage harness deleted the L3 rule and the SDK-path test
still passed. Both paths are asserted here, each with a green control, because a
fix whose test cannot fail is the defect this ticket family exists to prevent.

Split from `test_autonomy_ladder_git_global_opts.py` rather than appended: that
file reached 324 lines against the repo's 300-line convention, and the rule is
to extract when you touch it, never to raise its baseline entry.
"""
from __future__ import annotations

from app.server.tool_gate import decide
from swarm.nexus.autonomy_ladder import TIER_IRREVERSIBLE, TIER_LOCAL, classify


def is_denied(command: str) -> bool:
    """The SDK denylist path — `app.server.tool_gate`, SEGMENT_RULES."""
    return not decide("Bash", {"command": command}).allow


def tier(command: str) -> int:
    """The LIVE PreToolUse path — `classify`, L3_BASH_RE."""
    return classify("Bash", {"command": command})


SMUGGLED = [
    "git -c alias.z='reset --hard' z",
    "git -c alias.q='push --force' q",
    "git -c alias.d='clean -fdx' d",
]


# --------------------------------------------------------------------------
# the SDK denylist path
# --------------------------------------------------------------------------

def test_alias_smuggling_is_closed_on_the_sdk_path():
    """Flipped from a documented gap, exactly as that gap's docstring said to.

    `test_alias_smuggling_is_a_documented_boundary` used to assert
    `not is_denied(...)` and ended: "when it is fixed, it should flip to an
    assertion that the command is denied." It is fixed, so it has.

    The fix does not chase the payload. An alias definition is denied as a
    SHAPE, because an alias is an arbitrary-subcommand escape hatch and
    matching the verb inside its value is the game that produced this bug.
    """
    for command in SMUGGLED:
        assert is_denied(command), f"still smuggling: {command}"


def test_the_sdk_path_still_admits_ordinary_git():
    """GREEN CONTROL. A rule denying every `git` would satisfy the test above
    while making the gate useless — over-denial costs the loop ordinary git."""
    assert not is_denied("git status")
    assert not is_denied("git -C /repo log --oneline")
    assert not is_denied("git commit -m 'mentions alias.z in prose'")


# --------------------------------------------------------------------------
# the live hook path — the half that was actually enforcing
# --------------------------------------------------------------------------

def test_alias_smuggling_is_l3_on_the_live_hook_path():
    """The half `is_denied` cannot see, and the half that mattered in production."""
    for command in SMUGGLED:
        assert tier(command) == TIER_IRREVERSIBLE, f"L3 leak: {command}"


def test_the_live_hook_still_admits_ordinary_git():
    """GREEN CONTROL — the live path must not have been blanket-raised to L3."""
    assert tier("git -C /repo log --oneline") == TIER_LOCAL
    assert tier("git -c core.editor=true commit -m 'x'") == TIER_LOCAL


def test_the_direct_forms_are_unchanged():
    """Regression floor: closing the alias shape must not disturb what already
    worked. These were denied before this change and must stay denied."""
    assert tier("git push --force origin main") == TIER_IRREVERSIBLE
    assert tier("git -C /repo push --force origin main") == TIER_IRREVERSIBLE
    assert is_denied("git reset --hard")
