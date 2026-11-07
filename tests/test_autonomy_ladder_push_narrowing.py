"""RA-7383 — the push-rule narrowing, and the round that attacked it.

Split from `test_autonomy_ladder_l3_segments.py` under the 300-line rule. The
seam is real rather than arbitrary: that file is RA-7382's corpus — the
must-block commands from three failed narrowings, which any future attempt has
to clear — and this one is about the narrowing that finally worked and what it
costs. Read that file first; this one assumes its post-mortem.

WHAT DESIGN 4 DOES DIFFERENTLY. The three rejected designs each tried to REPLACE
the whole-line L3 match with a smarter regex, so every imperfection in the parse
REMOVED protection. Design 4 inverts that: the whole-line match stays
authoritative, and `swarm/nexus/push_targets.py` may only ever SUBTRACT a push
verdict, and only where the destination is certain. Certainty is defined by
refusal — any quote, `$`, backtick or backslash in the push segment, any
unrecognised flag, any missing refspec, any destination that is not a plain
literal branch name and the parse is abandoned. An imperfect parse now costs a
redundant approval prompt instead of a bypass.

WHY THE TESTS ARE SHAPED THE WAY THEY ARE. Three of the four things this suite
pins were found by measurement after the implementation looked finished, and
none of them by reading the diff:

* `git push origin HEAD` and `git push origin @` were LIVE LEAKS in the first
  draft. Both name whatever branch is checked out — possibly main — but the
  literal tokens `head` and `@` are not protected branch names, so the parser
  read them as safe and subtracted the verdict.
* A subtracted push fell into the read-only branch and scored L0, because
  `READ_ONLY_BASH` matches on the first command in a chain.
* A subtracted push then scored L1 rather than L2, because `L2_BASH` carries the
  same whole-line "no protected token" lookahead the L3 rules do.

The last two would have been invisible to a suite that only asked "is it L3?".
Hence `test_a_subtracted_push_is_still_an_outward_action`, which asserts the
exact tier: a narrowing that lands a push BELOW where the same push lands on its
own merits is not a narrowing, it is a second bug.

Every test that asserts a command must stay L3 uses a command that matches the
whole-line rule on its own — several carry a trailing `echo main` so that it
does. A case the whole-line rule never matched cannot demonstrate anything about
a change that only subtracts from it, and asserting L3 on one would be testing
RA-7409's gap while claiming to test this narrowing. Six such cases were written
into the first draft of this suite and failed for exactly that reason; they are
now asserted against the parser directly, which is where they bite.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    """Load a module by path; `swarm.nexus` need not be an importable package."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LADDER = _load("autonomy_ladder_narrowing", "swarm/nexus/autonomy_ladder.py")
RULES = _load("autonomy_rules_narrowing", "swarm/nexus/autonomy_rules.py")


def is_l3(command: str) -> bool:
    """Classify a Bash command through the canonical public entry point."""
    return LADDER.classify("Bash", {"command": command}) == LADDER.TIER_IRREVERSIBLE


# --- The RA-7382 residual, closed by RA-7383's design 4 ---------------------
#
# These three were `xfail(strict=True)` for exactly one ticket. They are the
# false positives the narrowing exists to remove: a push whose every refspec is
# provably a feature branch, with `main` appearing only in a read-only sibling
# command or a filename. Nothing here writes a protected ref.

@pytest.mark.parametrize("command", [
    "git push origin HEAD:refs/heads/claude/my-feature && git rev-parse --short origin/main",
    "git push -u origin feature/x && git log --oneline origin/main -1",
    "git push origin feature/x | tee main.log",
])
def test_feature_push_with_unrelated_main_token_is_not_l3(command):
    """A later `main` token must no longer make a safe push L3 (RA-7383)."""
    assert not is_l3(command), f"feature-branch push misclassified as L3: {command}"


# --- Adversarial round: attacks on design 4's parser ------------------------
#
# Written to break the narrowing rather than to confirm it, and it did: the first
# two cases were LIVE LEAKS in the first draft. `HEAD` and `@` name whatever
# branch is checked out — possibly main — but the literal tokens `head` and `@`
# are not protected branch names, so the parser read them as safe destinations
# and subtracted the verdict. Closed by refusing any destination that is not a
# plain literal branch name (`_UNRESOLVABLE_REFS`, `_PLAIN_REF_RE`).
#
# The rest passed first time and are kept because they pin the reasons WHY the
# parser refuses: an unknown flag may take a value and shift the positionals; a
# separator inside quotes is data; a colon-prefix is a deletion.

@pytest.mark.parametrize("command", [
    # Destination knowable only at runtime — the two that leaked.
    "git push origin HEAD && echo main",
    "git push origin @ && echo main",
    # Refspec forms that write a protected branch.
    "git push origin :main",                 # deletes main
    "git push origin feature/x:main",        # feature -> main
    "git push origin refs/heads/main",
    "git push origin +main",
    "git push origin MAIN",                  # case
    # Flags outside the value-less allowlist — positionals may have shifted.
    "git push origin --delete main",
    "git push -o ci.skip origin main",
    "git push --receive-pack=/x origin feature/y && echo main",
    # Destination shapes the parser must refuse rather than interpret.
    "git push origin 'refs/heads/*' && echo main",
    "git push origin @{-1} && echo main",
    "git push origin feature/x: && echo main",   # empty destination
    # Boundaries: quoting is data, and every push in a chain must clear.
    'git push origin feature/x "&& main"',
    "git push origin feature/x; git push origin main",
])
def test_adversarial_pushes_stay_l3(command):
    """Design 4 may only subtract where the target is certain. These are not.

    Every command here matches the whole-line rule on its own — the trailing
    `echo main` is there so it does. That is deliberate: a case the whole-line
    rule never matched cannot demonstrate anything about a change that only ever
    subtracts from it, and asserting L3 on one would be testing RA-7409's gap
    while claiming to test this narrowing. Six such cases were written into the
    first draft of this suite and failed for exactly that reason; they moved to
    the parser-level test below, which is where they actually bite.
    """
    assert is_l3(command), f"narrowing opened a bypass: {command}"


@pytest.mark.parametrize("command", [
    "git push origin HEAD",                       # current branch — may be main
    "git push -u origin @",                       # `@` is HEAD
    "git push origin @{-1}",                      # reflog selector
    "git push origin 'refs/heads/*'",             # glob
    "git push origin feature/x:",                 # empty destination
    "git push --receive-pack=/x origin feature/y",  # unknown flag may take a value
    "git push origin feature/x $EXTRA",           # substitution
    "git push origin feature/x `cat r`",          # backtick
    "git push origin",                            # no refspec at all
    "git push",                                   # nothing at all
    "git push --mirror origin",                   # no refspec; writes everything
    "; ".join(["git push origin feature/x"] * 40),  # over the occurrence bound
    "git push origin feature/" + "x" * 10_001,      # over the length bound
])
def test_parser_refuses_every_target_it_cannot_resolve(command):
    """The subtraction may only fire where the destination is literal and certain.

    Asserted against the parser rather than the tier because none of these carry
    a protected token, so `classify` never consults the parser for them — it is
    RA-7409 that leaves them at L2, not this change. They are pinned here anyway:
    the moment RA-7409 widens the rules, `classify` WILL start consulting the
    parser on exactly these shapes, and a parser that resolved `HEAD` to a safe
    branch would turn that widening straight back into a bypass.
    """
    assert not RULES.push_targets_are_all_unprotected(command), (
        f"parser claimed certainty about an unresolvable target: {command}"
    )


@pytest.mark.parametrize("command", [
    "git push origin feature/x",
    "git push -u origin feature/x",
    "git push --force-with-lease origin claude/setup-token-command-21xg74",
    "git push origin HEAD:refs/heads/claude/my-feature",   # HEAD as SOURCE is fine
    "git push origin main:feature/x",                      # FROM protected is fine
    "git push origin feature/a feature/b",
])
def test_parser_still_resolves_a_plainly_safe_push(command):
    """Positive control for the test directly above.

    Without it, a parser hard-wired to `return False` would pass every refusal
    case and look flawless. Note what stays allowed: `HEAD` as the SOURCE of a
    refspec resolves nothing about the destination, so it is not refused — only
    `HEAD` as the destination is.
    """
    assert RULES.push_targets_are_all_unprotected(command), (
        f"parser refused a plainly safe push, so the narrowing does nothing: {command}"
    )


@pytest.mark.parametrize("command", [
    "git push origin feature/x && git rev-parse origin/main",
    "git push origin main:feature/x && echo main",   # FROM protected, TO feature
    "git push origin feature/main && echo main",     # branch merely named that
])
def test_adversarial_green_control_still_subtracts(command):
    """Green control: the narrowing must still fire, or it fixed nothing.

    Without this, a parser that refused every command would score full marks on
    the block half above — the RA-7120 rule that a control never observed
    accepting anything is indistinguishable from one that always refuses.
    """
    assert not is_l3(command), f"narrowing stopped firing on a safe push: {command}"


# --- The subtraction must never land BELOW the command's own merits ---------

@pytest.mark.parametrize("command", [
    "git push origin feature/x && echo main",
    "git push origin HEAD:refs/heads/claude/my-feature && git rev-parse --short origin/main",
    "git push -u origin feature/x && git log --oneline origin/main -1",
    "git push origin feature/x | tee main.log",
    "git status && git push origin feature/x && echo main",
])
def test_a_subtracted_push_is_still_an_outward_action(command):
    """A cleared push drops to L2, never to L1 or L0. It is still a push.

    Two separate rules had to be floored for this to hold, and both were caught
    by measurement rather than by reading the diff:

    * `READ_ONLY_BASH` matches on the FIRST command in a chain, so
      `git status && git push ...` reached the read-only branch and scored L0 —
      a write classified as a read.
    * `L2_BASH`'s push pattern carries the SAME whole-line "no protected token"
      lookahead as the L3 rules, because L3 used to own every command with one.
      Subtracted pushes fall out of it too and scored L1 — strictly lower than
      the identical command with `hi` in place of `main`, which is L2.

    Both would have been invisible in a suite that only asked "is it L3?". A
    narrowing that lands a push below where the same push lands on its own
    merits is not a narrowing, it is a second bug.
    """
    tier = LADDER.classify("Bash", {"command": command})
    assert tier == LADDER.TIER_OUTWARD, (
        f"subtracted push landed at tier {tier}, expected "
        f"TIER_OUTWARD ({LADDER.TIER_OUTWARD}): {command}"
    )


# --- Known gap, older than this change, recorded rather than papered over ----

@pytest.mark.xfail(strict=True, reason=(
    "RA-7409: the push rules only see a protected branch when it is spelled on "
    "the line. `--mirror` and `--all` write every ref, naming none, so neither "
    "rule matches and the command classifies L2. Measured on `main` before any "
    "RA-7383 change, so this is a pre-existing gap and not a regression from "
    "the narrowing — the narrowing cannot reach it, because the whole-line rule "
    "it subtracts from never matched in the first place. Fixing it is a "
    "WIDENING (a new rule), tracked separately so it is reviewed as one. "
    "strict=True so RA-7409's fix flips this red and forces the note updated."
))
@pytest.mark.parametrize("command", [
    "git push --mirror origin",
    "git push --all origin",
])
def test_refspec_less_broadcast_push_is_l3(command):
    """Documented gap: a push that writes main without naming it is not L3."""
    assert is_l3(command), f"broadcast push not classified L3: {command}"
