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

    # Strategic, CLI-only L3 — KNOWN divergence the other way (CLI denies, SDK's
    # denylist does not cover it). Documented as a follow-up gap, pinned so it is
    # a deliberate, visible state and not an accident.
    ("Bash", {"command": "git merge origin/main"}, ladder.TIER_IRREVERSIBLE, False, True,
     "git merge: CLI-deny, SDK-gap"),
    ("Bash", {"command": "gh secret set K --body v"}, ladder.TIER_IRREVERSIBLE, False, True,
     "secret set: CLI-deny, SDK-gap"),
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
