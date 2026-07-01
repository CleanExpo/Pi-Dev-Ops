"""RA-6874 — autonomy-ladder tool-call gate: classifier + decision + hook tests."""
import json
import os
import subprocess
import sys

import pytest

from swarm.nexus.autonomy_gate import (
    TIER_IRREVERSIBLE,
    TIER_LOCAL,
    TIER_READ,
    classify,
    decide,
)


def bash(cmd):
    return ("Bash", {"command": cmd})


class TestClassifyL3:
    @pytest.mark.parametrize("cmd", [
        "git merge origin/main",
        "gh pr merge 603 --squash",
        "git push origin main",
        "git push --force origin main",
        "vercel deploy --prod",
        "vercel --prod",
        "vercel promote",
        "supabase db push",
        "prisma migrate deploy",
        "supabase migration up",
        "gh secret set OPENAI_KEY --body xxx",
        "vercel env add STRIPE_KEY production",
        "echo 'KEY=secret' > .env",
        "printf 'X=1\\n' >> apps/web/.env.local",
        "supabase projects create newthing",
        "gh repo create acme/new-service",
    ])
    def test_l3_bash_is_denied(self, cmd):
        assert classify(*bash(cmd)) == TIER_IRREVERSIBLE

    @pytest.mark.parametrize("name", [
        "mcp__claude_ai_Vercel__deploy_to_vercel",
        "mcp__claude_ai_Supabase__apply_migration",
        "mcp__claude_ai_Supabase__deploy_edge_function",
        "mcp__claude_ai_Supabase__create_project",
        "mcp__x__rotate_secret",
    ])
    def test_l3_tool_names(self, name):
        assert classify(name, {}) == TIER_IRREVERSIBLE


class TestClassifyPasses:
    @pytest.mark.parametrize("cmd", [
        "git push origin feat/uni-2220",
        "git push -u origin feat/ra-6874",
        "git commit -m 'fix: thing'",
        "git status",
        "git log --oneline -5",
        "gh pr checks 603 -R CleanExpo/Unite-Group",
        "gh pr create --title x --body y",
        "npx vitest run",
    ])
    def test_non_l3_bash_passes(self, cmd):
        assert classify(*bash(cmd)) < TIER_IRREVERSIBLE

    @pytest.mark.parametrize("name", ["Read", "Grep", "Glob", "WebFetch", "WebSearch"])
    def test_read_only_tools(self, name):
        assert classify(name, {}) == TIER_READ

    @pytest.mark.parametrize("name", ["Edit", "Write", "MultiEdit"])
    def test_local_write_tools(self, name):
        assert classify(name, {"file_path": "/x"}) == TIER_LOCAL

    def test_dot_env_example_is_not_l3(self):
        # editing the committed template is safe, not a secret write
        assert classify(*bash("echo 'KEY=' > .env.example")) < TIER_IRREVERSIBLE
        assert classify("Edit", {"file_path": "apps/web/.env.example"}) < TIER_IRREVERSIBLE

    def test_unknown_tool_defaults_below_l3(self):
        assert classify("mcp__claude_ai_Linear__save_issue", {}) < TIER_IRREVERSIBLE
        assert classify("mcp__claude_ai_Linear__list_issues", {}) < TIER_IRREVERSIBLE


class TestDecide:
    def test_l3_is_denied(self):
        d = decide(*bash("supabase db push"))
        assert d is not None
        assert d["permissionDecision"] == "deny"

    def test_l1_and_l2_pass_through(self):
        assert decide("Edit", {"file_path": "/x"}) is None
        assert decide(*bash("git push origin feat/x")) is None
        assert decide(*bash("gh pr create --title x")) is None

    def test_hard_stop_denies_everything_at_every_tier(self):
        for call in [("Read", {"file_path": "/x"}), bash("git status"),
                     bash("supabase db push")]:
            d = decide(*call, hard_stop=True)
            assert d is not None
            assert d["permissionDecision"] == "deny"
            assert "HARD_STOP" in d["permissionDecisionReason"]

    def test_reason_is_actionable(self):
        d = decide(*bash("git merge origin/main"))
        assert "L3" in d["permissionDecisionReason"]


HOOK = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".claude", "hooks",
                 "autonomy_gate_hook.py")
)


def _run_hook(payload):
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


class TestHookScript:
    def test_hook_exists(self):
        assert os.path.exists(HOOK)

    def test_hook_denies_l3(self):
        p = _run_hook({"tool_name": "Bash", "tool_input": {"command": "supabase db push"}})
        assert p.returncode == 0
        out = json.loads(p.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_silent_on_l1(self):
        p = _run_hook({"tool_name": "Bash", "tool_input": {"command": "git push origin feat/x"}})
        assert p.returncode == 0
        assert p.stdout.strip() == ""

    def test_hook_survives_garbage_input(self):
        p = subprocess.run([sys.executable, HOOK], input="not json",
                           capture_output=True, text=True)
        assert p.returncode == 0
        assert p.stdout.strip() == ""
