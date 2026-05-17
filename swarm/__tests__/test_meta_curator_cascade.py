"""Tests for the meta_curator SKILL.md composition cascade.

Locks the Max-first migration (task #180) — `claude --print` tier-0 must
run before the existing claude_agent_sdk tier-1, with the template stub
as final fallback. Same cascade pattern as preamble_trainer / pii_classify.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from swarm import meta_curator as mc


def _cluster(key="vague-pattern", summary="three rows of the same shape"):
    return mc.Cluster(
        cluster_id="abc123",
        source="lessons",
        key=key,
        summary=summary,
        evidence=[
            {"file": "a.py", "line": 10, "snippet": "x"},
            {"file": "b.py", "line": 20, "snippet": "y"},
            {"file": "c.py", "line": 30, "snippet": "z"},
        ],
    )


VALID_SKILL_MD = """---
name: curator-vague-pattern
description: One-liner.
owner_role: founder
status: proposed
---

# Why this exists

Body.
"""


class ClaudePrintTierTests(unittest.TestCase):
    """Tier 0 — `claude --print` (free under Max plan)."""

    def test_returns_body_on_success(self):
        fake = MagicMock(returncode=0, stdout=VALID_SKILL_MD, stderr="")
        with patch("swarm.meta_curator.subprocess.run", return_value=fake):
            body = mc._compose_skill_body_via_claude_print(_cluster(), "curator-vague-pattern")
        self.assertIsNotNone(body)
        self.assertTrue(body.startswith("---"))
        self.assertIn("status: proposed", body)

    def test_returns_none_when_cli_missing(self):
        with patch("swarm.meta_curator.subprocess.run", side_effect=FileNotFoundError("claude")):
            body = mc._compose_skill_body_via_claude_print(_cluster(), "curator-vague-pattern")
        self.assertIsNone(body)

    def test_returns_none_on_nonzero_exit(self):
        fake = MagicMock(returncode=1, stdout="", stderr="rate-limited")
        with patch("swarm.meta_curator.subprocess.run", return_value=fake):
            self.assertIsNone(mc._compose_skill_body_via_claude_print(_cluster(), "x"))

    def test_returns_none_on_empty_stdout(self):
        fake = MagicMock(returncode=0, stdout="   \n", stderr="")
        with patch("swarm.meta_curator.subprocess.run", return_value=fake):
            self.assertIsNone(mc._compose_skill_body_via_claude_print(_cluster(), "x"))

    def test_returns_none_on_missing_frontmatter(self):
        # Body looks like prose, not SKILL.md frontmatter — reject.
        fake = MagicMock(returncode=0, stdout="Sure, here's a draft...\n", stderr="")
        with patch("swarm.meta_curator.subprocess.run", return_value=fake):
            self.assertIsNone(mc._compose_skill_body_via_claude_print(_cluster(), "x"))

    def test_env_disable_short_circuits(self):
        prior = os.environ.get("DISABLE_CLAUDE_PRINT_CURATOR")
        os.environ["DISABLE_CLAUDE_PRINT_CURATOR"] = "1"
        try:
            with patch("swarm.meta_curator.subprocess.run") as subp:
                self.assertIsNone(mc._compose_skill_body_via_claude_print(_cluster(), "x"))
            subp.assert_not_called()
        finally:
            if prior is None:
                del os.environ["DISABLE_CLAUDE_PRINT_CURATOR"]
            else:
                os.environ["DISABLE_CLAUDE_PRINT_CURATOR"] = prior


class CascadeOrderTests(unittest.TestCase):
    """`_draft_skill_md_stub` must try tier 0 before tier 1 before template."""

    def test_tier_0_wins_no_sdk_call(self):
        with patch.object(mc, "_compose_skill_body_via_claude_print",
                          return_value=VALID_SKILL_MD) as tier0, \
             patch.object(mc, "_compose_skill_body_via_sdk") as tier1:
            name, body = mc._draft_skill_md_stub(_cluster())
        tier0.assert_called_once()
        tier1.assert_not_called()
        self.assertIn("status: proposed", body)
        self.assertTrue(name.startswith("curator-"))

    def test_falls_through_to_sdk_when_tier_0_returns_none(self):
        sdk_body = VALID_SKILL_MD.replace("Body.", "SDK body.")
        with patch.object(mc, "_compose_skill_body_via_claude_print", return_value=None) as tier0, \
             patch.object(mc, "_compose_skill_body_via_sdk", return_value=sdk_body) as tier1:
            name, body = mc._draft_skill_md_stub(_cluster())
        tier0.assert_called_once()
        tier1.assert_called_once()
        self.assertIn("SDK body", body)

    def test_falls_through_to_template_when_both_tiers_fail(self):
        with patch.object(mc, "_compose_skill_body_via_claude_print", return_value=None), \
             patch.object(mc, "_compose_skill_body_via_sdk", return_value=None):
            name, body = mc._draft_skill_md_stub(_cluster())
        # Template stub body starts with frontmatter too — just verify it's a string
        self.assertIsInstance(body, str)
        self.assertGreater(len(body), 100)
        self.assertTrue(name.startswith("curator-"))


class PromptSharedTests(unittest.TestCase):
    """Both tiers must use the same prompt — extracted into _build_skill_prompt."""

    def test_prompt_includes_cluster_metadata(self):
        prompt = mc._build_skill_prompt(_cluster(key="alpha-pattern", summary="example"), "curator-alpha-pattern")
        self.assertIn("curator-alpha-pattern", prompt)
        self.assertIn("alpha-pattern", prompt)
        self.assertIn("example", prompt)
        self.assertIn("lessons", prompt)  # source field

    def test_prompt_caps_evidence_at_five(self):
        c = _cluster()
        # Add more than 5 evidence items
        c.evidence = [{"id": i} for i in range(20)]
        prompt = mc._build_skill_prompt(c, "x")
        # Evidence ids 0-4 included; 5+ excluded
        for i in range(5):
            self.assertIn(f'"id": {i}', prompt)
        self.assertNotIn('"id": 5', prompt)


if __name__ == "__main__":
    unittest.main()
