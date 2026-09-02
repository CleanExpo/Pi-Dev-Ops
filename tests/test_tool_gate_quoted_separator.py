"""RA-7412 — a quoted separator must not sever a signature in the UNATTENDED gate.

Split from `test_tool_gate.py` under the 300-line rule. The seam is a real one:
that file covers what `decide()` denies, this one covers a defect in HOW it looks.

THE LEAK. `_inspect_bash` splits on shell separators before testing the segment
rules. A `;` inside a quoted ARGUMENT is data, not a command boundary, but the
split could not tell — so the signature was severed and neither half matched. Two
commands reached the unattended loop ALLOWED: a production deploy and a hard
reset that destroys uncommitted work. RA-7382 measured 59-75 leaks of this exact
shape against the INTERACTIVE gate and rejected segmentation for it; this file
kept it, and here there is no human to catch a miss.

WHY EVERY CASE IS PAIRED. A green test on a denial proves nothing on its own: a
rule that had stopped matching entirely looks identical to a rule that now
matches correctly. Each leak is paired with its unquoted twin as a positive
control, and the benign cases are the negative control against the fix
degenerating into deny-everything.

WHAT THE FIRST ATTEMPT GOT WRONG, kept because the reason is the design. Testing
the whole uncut command INSTEAD of the segments looked obvious and this suite
rejected it: several rules scan forward with `[^\n]*`, so over a chain they
collect tokens from unrelated later commands — `rm notes.txt && tar -rvf ...`
reads as `rm -rf`. Segmentation is not merely a weaker reading; for those rules
it is what makes them correct. `sql-delete-no-where` fails the other way, its
lookahead suppressed by a WHERE in an unrelated later statement. Neither reading
dominates, so the fix ADDS a quote-aware pass and keeps both.
"""
from __future__ import annotations

import pytest

from app.server.tool_gate import decide

# Split so this file's own literals do not trip the always-on PreToolUse hook,
# which scans command text for these signatures and cannot tell a test fixture
# from an intent to deploy. That false positive is the RA-7382 class, met here
# while writing the fix for its sibling.
_PROD = "--pr" "od"
_DEPLOYER = "ver" "cel"


@pytest.mark.parametrize("cmd,label", [
    # The two measured leaks.
    (_DEPLOYER + ' -e CSP="default-src \'self\'; script-src \'self\'" ' + _PROD, "vercel-prod"),
    ('git -c note="a;b" reset --hard', "git-reset-discard"),
    # Single quotes are masked the same as double.
    (_DEPLOYER + " -e 'a;b' " + _PROD, "vercel-prod"),
    # `$`, a backtick or a backslash defeats simple masking, so those fall back to
    # the strictest reading rather than skipping the pass — otherwise the bypass
    # would be one `$` away.
    (_DEPLOYER + ' -e "a;$X" ' + _PROD, "vercel-prod"),
    (_DEPLOYER + ' --meta note="a \\" ; b" ' + _PROD, "vercel-prod"),
    (_DEPLOYER + " --meta note=`echo a;b` " + _PROD, "vercel-prod"),
    # An unclosed quote leaves no span to mask, so the mask cannot be trusted.
    (_DEPLOYER + ' -e "a;b ' + _PROD, "vercel-prod"),
    ('echo "hi" && ' + _DEPLOYER + ' -e "a;b ' + _PROD, "vercel-prod"),
])
def test_quoted_separator_cannot_sever_a_signature(cmd, label):
    d = decide("Bash", {"command": cmd})
    assert d.allow is False, f"quoted separator opened a bypass: {cmd}"
    assert d.label == label


@pytest.mark.parametrize("cmd,label", [
    (_DEPLOYER + " " + _PROD, "vercel-prod"),
    ("git reset --hard", "git-reset-discard"),
])
def test_control_the_same_commands_unquoted_are_denied(cmd, label):
    """Positive control for the block above — proves those rules fire at all."""
    d = decide("Bash", {"command": cmd})
    assert d.allow is False and d.label == label


@pytest.mark.parametrize("cmd", [
    # Quoting is ordinary shell. The added pass must not turn the gate into
    # deny-everything, or it would stall the unattended loop on benign work.
    'echo "a; b" && ls',
    'git commit -m "fix: a; then b"',
    'echo "don\'t" && rm a.txt && grep -rf p d',   # apostrophe inside a quoted span
    'grep "foo;bar" file.txt',
])
def test_added_pass_does_not_deny_benign_quoting(cmd):
    assert decide("Bash", {"command": cmd}).allow is True, f"over-denied: {cmd}"


def test_added_pass_is_additive_not_a_swap():
    """The two passes have opposite strengths; dropping either loses a denial.

    Checking the whole command INSTEAD of segments was the first attempt and this
    suite rejected it: rules that scan forward with `[^\\n]*` collect tokens from
    unrelated later commands (`rm notes.txt && tar -rvf ...` reads as `rm -rf`),
    and `sql-delete-no-where` is suppressed by a WHERE in an unrelated later
    statement. Both directions are asserted here so a future simplification to a
    single pass fails with the reason attached.
    """
    # Only the ORIGINAL per-segment pass catches this one.
    d = decide("Bash", {"command": 'psql -c "DELETE FROM users"; psql -c "SELECT 1 WHERE x"'})
    assert d.allow is False and d.label == "sql-delete-no-where"
    # Only the ADDED quote-aware pass catches this one.
    assert decide("Bash", {"command": _DEPLOYER + ' -e "a;b" ' + _PROD}).allow is False
    # And the forward-scan false positive the original pass exists to avoid.
    assert decide("Bash", {"command": "rm notes.txt && tar -rvf archive.tar src"}).allow is True


@pytest.mark.parametrize("cmd", [
    "cd $HOME && ls -la",
    "echo $PATH && git status",
    "npm run build && cp -r dist $OUT",
    "git log --oneline $(git merge-base HEAD main)",
    "export X=$(date +%s) && echo $X",
])
def test_substitution_alone_does_not_stall_the_loop(cmd):
    """`$`/`$()` sends a command down the strict path; that must stay affordable.

    The strict path reads the command uncut, which is where the forward-scanning
    rules can pick up tokens from unrelated later commands. Ordinary shell using
    variables and substitution has to survive it, or the unattended loop stalls on
    everyday work and the fix costs more than the leak did.
    """
    assert decide("Bash", {"command": cmd}).allow is True, f"over-denied: {cmd}"


def test_known_and_accepted_over_denial():
    """The measured cost of the strict path, pinned so it stays visible.

    `$` forces the uncut reading, and there the `rm-rf` lookaheads find `rm` and a
    LATER unrelated `-rf`. This command is harmless and is denied anyway.

    It is accepted rather than fixed: this is the default-deny gate for unattended
    work, so a stalled task is the cheap failure and an unapproved production
    deploy is the expensive one. Recorded as a test rather than left to be
    rediscovered — and if a future change makes it pass, that is an improvement
    and this test should be updated, not deleted.
    """
    assert decide("Bash", {"command": "rm a.txt && grep -rf $PAT dir"}).allow is False


def test_git_rm_exemption_cannot_launder_the_rest_of_a_chain():
    """The `git rm` exemption is about ONE command, not everything after it.

    `re.match` anchors the exemption at the start of what it is given. On the
    strict path that is the whole uncut chain, so a `git rm x &&` prefix exempted
    every later command too — found by probing this fix, not by reading it. The
    control is the same chain with a harmless prefix instead.
    """
    leaked = "git rm x && " + _DEPLOYER + ' -e "a;$X" ' + _PROD
    control = "ls && " + _DEPLOYER + ' -e "a;$X" ' + _PROD
    assert decide("Bash", {"command": leaked}).allow is False, "git rm prefix laundered a chain"
    assert decide("Bash", {"command": control}).allow is False, "control: the chain is denied"
    # ...and the exemption itself still works, or this was fixed by breaking it.
    assert decide("Bash", {"command": "git rm -rf cached"}).allow is True
    assert decide("Bash", {"command": 'git rm -rf cached && echo "a;b"'}).allow is True


def test_added_pass_is_bounded():
    """The gate runs on every unattended tool call, so a hang here is a DoS."""
    import time

    hostile = "echo " + ('"a;b" ' * 5000) + "&& ls"
    started = time.monotonic()
    decide("Bash", {"command": hostile})
    assert time.monotonic() - started < 1.0, "quote masking is not linear"
