"""RA-7382 — L3 Bash signatures must match the ACTION, not the line's text.

Two patterns in `swarm/nexus/autonomy_ladder.py` classified on raw line text:

1. ``\\bgit\\s+merge\\b`` matched ``git merge-base`` — a read-only ancestry query.
   The gate blocked precisely the safety check an agent should run *before*
   deciding whether a push is redundant, pushing it toward weaker evidence.
   **Fixed** with a negative lookahead.
2. The push rules' ``[^\\n]*`` gap spans the whole line, so any later ``main``
   token supplies the match. A feature-branch push chained with a read-only
   ``git rev-parse origin/main`` classifies L3 though nothing touches a
   protected ref. **Fixed in RA-7383 by design 4** — see below.

Both are fail-closed: the cost is lost capability, not unsafe passage. A fix is
therefore held to a strict standard — it may only remove false positives, never
add a bypass. Three designs failed that bar, each killed by measurement:

1. Split the command on shell separators, test each segment. Quote-blind: a
   separator inside a quoted ARGUMENT severs the signature and neither half
   matches. 59-75 leaks against a bash-oracle corpus, including a production
   ``vercel -e CSP="...; ..." --prod`` and a branch-protection DELETE.
2. Mask quoted spans, then split. Escaped quotes, backticks, ``${...}``,
   ANSI-C ``$'...'`` and a bare ``a\\;b`` still leaked, 75 cases. A hand-rolled
   scanner tracking quote and nesting depth still leaked 15.
3. Constrain the *gap* to a repetition of one shell-argument-shaped unit so it
   cannot traverse a bare separator. Shipped, then caught in review: a quoted
   span is consumed WHOLE, so a quoted protected ref is swallowed by the gap and
   the trailing ``(main|master|prod|production)`` can never match.
   ``git push origin "main"`` dropped L3 to L1 — 18 in that class, every one
   ordinary bash needing no adversarial intent. Letting the gap cross quote
   characters closes it and turns the pattern catastrophically backtracking
   (42 s on 18 quoted arguments — a DoS inside a PreToolUse hook).

Design 4 (RA-7383) cleared the bar by **inverting the failure direction**. The
whole-line match stays authoritative and is never weakened; a separate parser
(``autonomy_rules.push_targets_are_all_unprotected``) may only ever SUBTRACT a
push verdict, and only when it is certain. Certainty is defined by refusal: any
quote, ``$``, backtick or backslash in the push segment, any unrecognised flag,
any missing refspec, any destination that is not a plain branch name — the parse
is abandoned and the whole-line verdict stands. That single rule retires all
three earlier leak classes at once, because every one of them is a command this
refuses to reason about. An imperfect parse now costs a redundant prompt instead
of a bypass, which is what the first three designs could not offer.

The must-block half of this suite is the load-bearing half: it carries every
reproducing command from all three review rounds plus the adversarial round that
attacked design 4 itself, so any future narrowing has to clear all of them at
once. Two of those adversarial cases were live leaks in design 4's first draft
(``git push origin HEAD`` and ``git push origin @`` — both name whatever branch
is checked out, which may be main) and were found by probe, not by review.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ladder():
    """Load the ladder module directly; `swarm.nexus` need not be importable."""
    spec = importlib.util.spec_from_file_location(
        "autonomy_ladder_under_test", REPO_ROOT / "swarm" / "nexus" / "autonomy_ladder.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _rules():
    """Load the rule table module directly, for parser-level assertions."""
    spec = importlib.util.spec_from_file_location(
        "autonomy_rules_under_test", REPO_ROOT / "swarm" / "nexus" / "autonomy_rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LADDER = _ladder()
RULES = _rules()


def is_l3(command: str) -> bool:
    """Classify a Bash command through the canonical public entry point."""
    return LADDER.classify("Bash", {"command": command}) == LADDER.TIER_IRREVERSIBLE


# --- Defect 1: read-only merge-* porcelain must not be L3 -------------------

@pytest.mark.parametrize("command", [
    "git merge-base --is-ancestor abc123 def456",
    "git merge-base HEAD origin/main",
    "git merge-file a.txt b.txt c.txt",
    "git merge-tree HEAD origin/main",
])
def test_read_only_merge_porcelain_is_not_l3(command):
    """`git merge-base` and friends write nothing; blocking them cost evidence."""
    assert not is_l3(command), f"read-only command misclassified as L3: {command}"


@pytest.mark.parametrize("command", [
    "git merge main",
    "git merge --no-ff feature/x",
    "git merge origin/main",
    "git merge",
    "git merge --abort",
])
def test_real_merge_is_still_l3(command):
    """The actual merge verb must remain L3 — the half that must not slip."""
    assert is_l3(command), f"real merge no longer L3: {command}"


# --- The leak class that killed design 3 ------------------------------------
#
# A protected ref is a protected ref however it is spelled. Quoting a branch
# name is ordinary shell, not an attack, which is what made this the worst of
# the three: the bypass sits on the happy path. Every command below is valid
# bash verified with `bash -n`, and every one classified L1 under the shipped
# argument-unit gap. They pin the class permanently.

@pytest.mark.parametrize("command", [
    'git push origin "main"',
    "git push origin 'main'",
    "git push 'origin' 'main'",
    'git push origin "master"',
    'git push origin "prod"',
    'git push origin "production"',
    'git push origin "refs/heads/main"',
    'git push --force origin "main"',
    'git push --force-with-lease origin "master"',
    "git push -u origin 'main'",
    'git push -q origin "main"',
    'git push --set-upstream origin "main"',
    "git push origin `echo main`",
    'git push origin "$BR" main',
])
def test_quoted_protected_ref_is_still_l3(command):
    """A quoted protected ref must not slip past the gate (design-3 leak)."""
    assert is_l3(command), f"quoted protected ref opened a bypass: {command}"


# --- The bypass class that killed designs 1 and 2 ---------------------------
#
# A separator inside a quoted ARGUMENT is data, not a command boundary. Two
# review rounds found 75 real leaks here when the implementation segmented the
# command. These are the exact reproducing commands, verified by a bash oracle
# as single commands with the separator inert.

@pytest.mark.parametrize("command", [
    # Plain quoting — semicolons as CSP grammar, in a production deploy.
    "vercel -e CSP=\"default-src 'self'; script-src 'self'\" --prod",
    'vercel --meta note="RA-7382; approved by phill" --prod',
    'vercel --scope "acme; team" promote dpl_abc123',
    'gh api -f "reason=temporarily disabling; will restore" '
    'repos/CleanExpo/Pi-Dev-Ops/branches/main/protection -X DELETE',
    'git push --force -o "reason=hotfix; urgent" origin main',
    'git push -o "ci.skip;now" origin main',
    "git push -o 'note=a && b' origin main",
    'git push -o "note=a || b" origin main',
    # Escaped quote inside a quoted span — round 2's headline leak.
    'vercel --meta note="deploy \\" ; then verify" --prod',
    'gh api -f "note=said \\" ; proceed" repos/o/r/branches/main/protection -X DELETE',
    # Backticks, ${...}, ANSI-C quoting, and a bare escaped separator.
    'vercel --meta note=`echo a; echo b` --prod',
    'vercel --meta note=${VAR:-a;b} --prod',
    "vercel --meta note=$'a\\'; b' --prod",
    'vercel --meta note=a\\;b --prod',
    'vercel --meta note=$(echo a || echo b) --prod',
    'echo "a; b" > .env',
])
def test_separator_inside_an_argument_cannot_sever_a_signature(command):
    """A quoted, substituted or escaped separator is data, not a boundary."""
    assert is_l3(command), f"in-argument separator opened a bypass: {command}"


@pytest.mark.parametrize("command", [
    "git push origin main",
    "git push origin HEAD:refs/heads/main",
    "git push origin HEAD:main",
    "git push origin master",
    "git push origin production",
    "git push --force origin main",
    "git push --force-with-lease origin master",
    'git push "$(git remote | head -1)" main',
])
def test_push_to_protected_branch_is_still_l3(command):
    """Pushing to a protected branch must remain L3, in every spelling tested."""
    assert is_l3(command), f"protected-branch push no longer L3: {command}"


@pytest.mark.parametrize("command", [
    "echo hi && git push origin main",
    "git push origin feature/x && git push origin main",
    "git status; git push origin main",
    "git push origin feature/x || git push origin main",
])
def test_l3_later_in_a_chain_is_still_caught(command):
    """A real L3 anywhere in a chain must still be caught."""
    assert is_l3(command), f"chained L3 escaped detection: {command}"


@pytest.mark.parametrize("command", [
    "git push  origin  main",
    "vercel   --prod",
    "git   merge   main",
])
def test_extra_whitespace_does_not_sever_a_signature(command):
    """Guards against any implementation treating whitespace runs as boundaries."""
    assert is_l3(command), f"whitespace severed a signature: {command}"


# --- Non-regression across the rest of the L3 set ---------------------------

@pytest.mark.parametrize("command", [
    "gh pr merge 123",
    "vercel deploy",
    "vercel --prod",
    "supabase db push",
    "prisma migrate deploy",
    "supabase migration up",
    "gh secret set MY_TOKEN",
    "vercel env add SECRET",
    "gh repo create newthing",
    "supabase projects create thing",
    "vercel project add thing",
    "gh api repos/o/r/branches/main/protection",
    "echo x > .env",
])
def test_other_l3_signatures_unchanged(command):
    """Every other L3 signature must still classify L3 after the change."""
    assert is_l3(command), f"L3 signature regressed: {command}"


@pytest.mark.parametrize("command", [
    "echo x > .env.example",
    "git status",
    "git push origin feature/x",
    "git log --oneline origin/main -5",
    "git rev-parse origin/main",
    "git merge-base --is-ancestor HEAD origin/main",
])
def test_benign_commands_are_not_l3(command):
    """Read-only and feature-scoped work stays below the L3 bar."""
    assert not is_l3(command), f"benign command misclassified as L3: {command}"


def test_file_edits_remain_local_tier():
    """Editing a file is local and reversible — unchanged by this fix."""
    assert LADDER.classify("Edit", {"file_path": "x.py"}) == LADDER.TIER_LOCAL
    assert LADDER.classify("Write", {"file_path": "x.py"}) == LADDER.TIER_LOCAL


@pytest.mark.parametrize("hostile", [
    "git push " + ("\\a" * 2000) + " origin feature/x",
    "git push " + ('"a" ' * 2000) + "origin feature/x",
    "git push " + ("'a' " * 2000) + "origin feature/x",
])
def test_l3_matching_is_not_catastrophically_backtracking(hostile):
    """The L3 set runs in a PreToolUse hook, so a hang here is a DoS.

    Design 3's repair — a gap allowed to cross quote characters — took 42s on
    18 quoted arguments. A whole-line gap has no nested quantifier and stays
    linear; these bounds fail loudly if a future narrowing reintroduces one.
    """
    started = time.monotonic()
    is_l3(hostile)
    assert time.monotonic() - started < 1.0, "L3 matching backtracks catastrophically"
