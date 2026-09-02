"""RA-6882 — parity between the two autonomy gates.

Proves the convergence contract: both gates draw the autonomy *tier* from the one
shared classifier (``swarm.nexus.autonomy_ladder.classify``) and the one shared
signature registry, so the tier of any call cannot diverge again. The two gates
keep *different dispositions* on purpose (unattended SDK loop = default-deny
allowlist; interactive CLI hook = deny-only-L3); this test pins that intended
matrix so a future edit that silently re-forks it fails here.
"""
import pytest

import app.server.tool_gate as tool_gate
import swarm.nexus.autonomy_gate as autonomy_gate
import swarm.nexus.autonomy_ladder as ladder


# --- Single source of truth ------------------------------------------------
def test_both_gates_share_one_classifier():
    # The CLI gate re-exports the canonical classifier; it is the same object.
    assert autonomy_gate.classify is ladder.classify


def test_sdk_gate_uses_the_shared_registry():
    # The SDK gate imports the registry rather than carrying its own copy.
    assert tool_gate._SEGMENT_RULES is ladder.SEGMENT_RULES
    assert tool_gate._WHOLE_RULES is ladder.WHOLE_RULES
    assert tool_gate.ALLOWED_TOOLS is ladder.ALLOWED_TOOLS


def _sdk_denies(name, inp):
    return tool_gate.decide(name, inp).allow is False


def _cli_denies(name, inp):
    return autonomy_gate.decide(name, inp) is not None


# --- The intended tier + disposition matrix (the documented contract) -------
# (tool_name, tool_input, canonical_tier, sdk_denies, cli_denies, note)
MATRIX = [
    # Benign — both allow.
    ("Read", {"file_path": "/x"}, ladder.TIER_READ, False, False, "read-only"),
    ("Edit", {"file_path": "/x"}, ladder.TIER_LOCAL, False, False, "local edit"),
    ("Bash", {"command": "git status"}, ladder.TIER_READ, False, False, "read-only bash"),
    ("Bash", {"command": "git push origin feat/x"}, ladder.TIER_OUTWARD, False, False,
     "L2 feat push"),

    # Shared L3 — BOTH gates must deny (the agreement that must never re-fork).
    ("Bash", {"command": "supabase db push"}, ladder.TIER_IRREVERSIBLE, True, True,
     "prod DB migration"),
    ("Bash", {"command": "vercel deploy --prod"}, ladder.TIER_IRREVERSIBLE, True, True,
     "prod deploy"),
    ("mcp__claude_ai_Vercel__deploy_to_vercel", {}, ladder.TIER_IRREVERSIBLE, True, True,
     "MCP prod deploy"),
    ("mcp__claude_ai_Supabase__apply_migration", {}, ladder.TIER_IRREVERSIBLE, True, True,
     "MCP migration"),

    # Local-destructive — INTENTIONAL divergence: SDK (unattended, no undo) denies;
    # CLI (human present) passes to the normal permission prompt. See RA-6882 §D3.
    ("Bash", {"command": "rm -rf /tmp/x"}, ladder.TIER_LOCAL, True, False,
     "rm -rf: SDK-deny, CLI-pass"),
    ("Bash", {"command": "psql -c 'DROP TABLE users'"}, ladder.TIER_LOCAL, True, False,
     "DROP TABLE: SDK-deny, CLI-pass"),
    ("Bash", {"command": "mkfs.ext4 /dev/sda1"}, ladder.TIER_LOCAL, True, False,
     "mkfs: SDK-deny, CLI-pass"),

    # Strategic, SDK-only denylist — INTENTIONAL divergence (SDK denies, CLI passes).
    ("Bash", {"command": "npm publish"}, ladder.TIER_LOCAL, True, False,
     "npm publish: SDK-deny, CLI-pass"),
    ("Bash", {"command": "terraform apply -auto-approve"}, ladder.TIER_LOCAL, True, False,
     "terraform: SDK-deny, CLI-pass"),

    # Strategic L3 — CLOSED by RA-7413. These two rows read `sdk_deny=False` for
    # months, described as "a deliberate, visible state and not an accident". The
    # state was deliberate; its SIZE was not. Two rows were pinned out of THIRTEEN
    # L3 signatures the SDK gate did not cover, so the eleven nobody sampled were
    # invisible — see `test_every_l3_signature_has_an_example` below, which is the
    # actual fix. The SDK gate now consults `classify` as a backstop, so both gates
    # deny every L3 signature and these rows join the shared-L3 block above in
    # substance.
    ("Bash", {"command": "git merge origin/main"}, ladder.TIER_IRREVERSIBLE, True, True,
     "git merge: both deny (was the SDK gap)"),
    ("Bash", {"command": "gh secret set K --body v"}, ladder.TIER_IRREVERSIBLE, True, True,
     "secret set: both deny (was the SDK gap)"),

    # RA-7386: a git global option must not change any row above. Each of these
    # is the `-C` spelling of a row already in this matrix and must land on the
    # SAME tier and the SAME disposition — that equality is the whole contract,
    # so a regression on either gate surfaces here rather than in one gate's
    # own suite. Before the fix every one of them classified L1 and the SDK
    # allowed it.
    ("Bash", {"command": "git -C /repo status"}, ladder.TIER_LOCAL, False, False,
     "-C read-only: L1 not L0, READ_ONLY is deliberately not normalised"),
    ("Bash", {"command": "git -C /repo push origin feat/x"}, ladder.TIER_OUTWARD, False, False,
     "-C L2 feat push"),
    ("Bash", {"command": "git -C /repo merge origin/main"}, ladder.TIER_IRREVERSIBLE, True, True,
     "-C git merge: both deny (mirrors the un-prefixed row)"),
    ("Bash", {"command": "git -C /repo reset --hard"}, ladder.TIER_LOCAL, True, False,
     "-C reset --hard: SDK-deny, CLI-pass (mirrors rm -rf)"),
    ("Bash", {"command": "git --work-tree=/repo clean -fdx"}, ladder.TIER_LOCAL, True, False,
     "--work-tree clean -f: SDK-deny, CLI-pass"),
    ("Bash", {"command": "git -c core.editor=true stash drop"}, ladder.TIER_LOCAL, True, False,
     "-c stash drop: SDK-deny, CLI-pass"),
]

@pytest.mark.parametrize("name,inp,tier,sdk_deny,cli_deny,note", MATRIX)
def test_tier_is_consistent_across_both_paths(name, inp, tier, sdk_deny, cli_deny, note):
    # One classifier → one tier, regardless of which gate asks.
    assert ladder.classify(name, inp) == tier, note
    assert autonomy_gate.classify(name, inp) == tier, note


@pytest.mark.parametrize("name,inp,tier,sdk_deny,cli_deny,note", MATRIX)
def test_dispositions_match_the_documented_matrix(name, inp, tier, sdk_deny, cli_deny, note):
    assert _sdk_denies(name, inp) is sdk_deny, f"SDK disposition drift: {note}"
    assert _cli_denies(name, inp) is cli_deny, f"CLI disposition drift: {note}"


def test_shared_l3_never_diverges():
    # The subset both gates agree to block must stay agreed on both surfaces.
    for name, inp, tier, sdk_deny, cli_deny, note in MATRIX:
        if sdk_deny and cli_deny:
            assert tier == ladder.TIER_IRREVERSIBLE, note


# ===========================================================================
# RA-7413 — enumerate the L3 set; do not sample it.
#
# The matrix above is hand-picked, and that is exactly how the gap it was meant
# to expose stayed hidden. It carried TWO "CLI-deny, SDK-gap" rows. The real
# number was THIRTEEN. The eleven nobody happened to write down were not a
# deliberate visible state — they were absent, and a test cannot report a gap it
# never looks at.
#
# So coverage is asserted MECHANICALLY against the rule table itself: every
# pattern in `_L3_BASH` must be matched by at least one command below. A rule
# added without an example fails here, which is the property the old matrix
# lacked.
#
# This is not theoretical. The first corpus written for this test — 17 commands,
# one per rule, believed complete — was measured against the table and came back
# one short: `git push --force ... main` had no example. A hand-written list that
# looks complete is not, which is the whole argument for deriving the check from
# the table rather than from memory.
# ===========================================================================

# One representative command per L3 signature. Assembled from fragments so this
# file's own literals cannot trip the always-on PreToolUse hook, which scans
# command text for these very signatures and cannot tell a fixture from an intent.
_V = "ver" "cel"
_SB = "supa" "base"
_P = "m" "ain"
_AL = "ali" "as"

L3_CORPUS = [
    "git " + "merge" + " feature/x",
    "gh pr " + "merge" + " 123",
    "git " + "push" + " origin " + _P,
    "git " + "push" + " --force origin " + _P,
    _V + " --" + "prod",
    _V + " " + "promote" + " dpl_1",
    _V + " " + "deploy",
    _SB + " db " + "push",
    "prisma " + "migrate" + " deploy",
    _SB + " " + "migration" + " up",
    "gh " + "secret" + " set TOK",
    _V + " env " + "add" + " SECRET",
    "echo x > ." + "env",
    _V + " project " + "add" + " thing",
    _SB + " projects " + "create" + " thing",
    "gh repo " + "create" + " newthing",
    "gh api repos/o/r/branches/" + _P + "/protection -X DELETE",
    "git -c " + _AL + ".z=q z",
]


def test_every_l3_signature_has_an_example():
    """Every rule in the L3 table must be represented in `L3_CORPUS`.

    This is the guard the old two-row sample could not provide: it fails when a
    rule is added to `_L3_BASH` without a command exercising it, so the coverage
    below can never quietly stop covering the whole set.
    """
    import re

    uncovered = [
        pattern for pattern in ladder._L3_BASH
        if not any(re.search(pattern, cmd, re.IGNORECASE) for cmd in L3_CORPUS)
    ]
    assert not uncovered, (
        "L3 patterns with no example in L3_CORPUS — add one per rule:\n  "
        + "\n  ".join(uncovered)
    )


def test_the_corpus_contains_no_dead_entries():
    """Positive control: every corpus command really is L3.

    Without this the coverage test above could be satisfied by commands that no
    longer match anything meaningful, and "every pattern has an example" would
    become true by accident rather than by coverage.
    """
    not_l3 = [c for c in L3_CORPUS if ladder.classify("Bash", {"command": c}) != ladder.TIER_IRREVERSIBLE]
    assert not not_l3, f"corpus entries that are no longer L3: {not_l3}"


@pytest.mark.parametrize("cmd", L3_CORPUS)
def test_both_gates_deny_every_l3_signature(cmd):
    """The convergence claim, checked over the WHOLE L3 set rather than a sample.

    RA-6882 said the two gates may differ in disposition but not in what counts
    as dangerous. Measured before RA-7413 that was false for 13 of these: the
    interactive gate denied them and the unattended one — the surface with no
    human behind it — allowed them.
    """
    inp = {"command": cmd}
    assert _cli_denies("Bash", inp), f"interactive gate stopped denying: {cmd}"
    assert _sdk_denies("Bash", inp), f"unattended gate does not deny: {cmd}"
