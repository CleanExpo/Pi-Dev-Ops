"""Tests for swarm.pii_classify cascade.

Lock the Max-first cost-strategy migration (task #177): tier 0 must be
`claude --print` (free under Max plan); tier 1 is Anthropic API; both must
go through the shared _parse_spans validator so span/offset/category
guarantees are identical across tiers.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from swarm import pii_classify as pc


SAMPLE_TEXT = "Met with John Smith about the Q3 budget."
# offsets: J=9, e=10, .., John Smith = chars 9..19
SAMPLE_HIT = {
    "start": 9,
    "end": 19,
    "category": "name",
    "value": "John Smith",
}


class ParseSpansTests(unittest.TestCase):
    def test_returns_empty_on_empty_array(self):
        self.assertEqual(pc._parse_spans("[]", SAMPLE_TEXT), [])

    def test_returns_empty_on_blank(self):
        self.assertEqual(pc._parse_spans("", SAMPLE_TEXT), [])

    def test_returns_empty_on_invalid_json(self):
        self.assertEqual(pc._parse_spans("not json", SAMPLE_TEXT), [])

    def test_strips_code_fence(self):
        wrapped = "```json\n[" + json.dumps(SAMPLE_HIT) + "]\n```"
        hits = pc._parse_spans(wrapped, SAMPLE_TEXT)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].category, "NAME")
        self.assertEqual(hits[0].replacement, "[NAME-REDACTED]")

    def test_rejects_unknown_category(self):
        bad = dict(SAMPLE_HIT, category="not_a_real_category")
        self.assertEqual(pc._parse_spans(json.dumps([bad]), SAMPLE_TEXT), [])

    def test_rejects_offset_mismatch(self):
        # Model claims span 9..19 is "Carol Lee" but the actual substring at
        # those offsets is "John Smith" — must reject (anti-hallucination).
        bad = dict(SAMPLE_HIT, value="Carol Lee")
        self.assertEqual(pc._parse_spans(json.dumps([bad]), SAMPLE_TEXT), [])

    def test_maps_all_four_categories(self):
        text = "Attendees: A B, C D. Met at 12 Main Street. Project codename: orca."
        spans = [
            {"start": 0,  "end": 9,  "category": "attendee_list", "value": "Attendees"},  # contrived but matches
            {"start": 28, "end": 42, "category": "location",      "value": "12 Main Street"},
            {"start": 62, "end": 66, "category": "org_internal",  "value": "orca"},
        ]
        hits = pc._parse_spans(json.dumps(spans), text)
        # Validate each tier's substring matches at the asserted offsets.
        # (If the text setup is wrong, the parser correctly rejects — guards
        # against test-author hallucinating offsets the same way it would a
        # model.)
        for s in spans:
            self.assertEqual(text[s["start"]:s["end"]], s["value"], f"offset setup wrong for {s}")
        categories = sorted(h.category for h in hits)
        self.assertEqual(categories, ["ATTENDEES", "LOCATION", "ORG_INTERNAL"])


class ClaudePrintTierTests(unittest.TestCase):
    def test_returns_parsed_hits_on_success(self):
        fake = MagicMock(returncode=0, stdout=json.dumps([SAMPLE_HIT]), stderr="")
        with patch("swarm.pii_classify.subprocess.run", return_value=fake):
            hits = pc._classify_via_claude_print(SAMPLE_TEXT)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].category, "NAME")

    def test_raises_when_cli_missing(self):
        with patch("swarm.pii_classify.subprocess.run", side_effect=FileNotFoundError("claude")):
            with self.assertRaises(pc._ClassifyError):
                pc._classify_via_claude_print(SAMPLE_TEXT)

    def test_raises_on_nonzero_exit(self):
        fake = MagicMock(returncode=1, stdout="", stderr="rate-limited")
        with patch("swarm.pii_classify.subprocess.run", return_value=fake):
            with self.assertRaises(pc._ClassifyError) as cm:
                pc._classify_via_claude_print(SAMPLE_TEXT)
        self.assertIn("exit 1", str(cm.exception))


class CascadeTests(unittest.TestCase):
    """End-to-end: default_classifier wires tier 0 → tier 1 correctly."""

    def test_tier_0_wins_when_claude_print_succeeds(self):
        fake = MagicMock(returncode=0, stdout=json.dumps([SAMPLE_HIT]), stderr="")
        # If tier 0 succeeds, tier 1 must NOT be called.
        with patch("swarm.pii_classify.subprocess.run", return_value=fake), \
             patch("swarm.pii_classify._make_classifier_with_anthropic") as fake_t1:
            classifier = pc.default_classifier()
            hits = classifier(SAMPLE_TEXT)
        # _make_classifier_with_anthropic is called once during setup, but
        # the returned closure shouldn't be invoked when tier 0 wins.
        fake_t1.return_value.assert_not_called()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].category, "NAME")

    def test_falls_through_to_anthropic_when_claude_print_fails(self):
        # tier 0: FileNotFoundError. tier 1: returns one hit.
        tier1_closure = MagicMock(return_value=[
            pc.Hit(category="NAME", start=9, end=19, method="classify", replacement="[NAME-REDACTED]")
        ])
        with patch("swarm.pii_classify.subprocess.run", side_effect=FileNotFoundError("claude")), \
             patch("swarm.pii_classify._make_classifier_with_anthropic", return_value=tier1_closure):
            classifier = pc.default_classifier()
            hits = classifier(SAMPLE_TEXT)
        tier1_closure.assert_called_once_with(SAMPLE_TEXT)
        self.assertEqual(len(hits), 1)

    def test_skip_tier_0_when_env_disables_it(self):
        tier1_closure = MagicMock(return_value=[])
        prior = os.environ.get("DISABLE_CLAUDE_PRINT_CLASSIFIER")
        os.environ["DISABLE_CLAUDE_PRINT_CLASSIFIER"] = "1"
        try:
            with patch("swarm.pii_classify.subprocess.run") as subp_mock, \
                 patch("swarm.pii_classify._make_classifier_with_anthropic", return_value=tier1_closure):
                classifier = pc.default_classifier()
                classifier(SAMPLE_TEXT)
            subp_mock.assert_not_called()
            tier1_closure.assert_called_once_with(SAMPLE_TEXT)
        finally:
            if prior is None:
                del os.environ["DISABLE_CLAUDE_PRINT_CLASSIFIER"]
            else:
                os.environ["DISABLE_CLAUDE_PRINT_CLASSIFIER"] = prior

    def test_short_text_returns_empty_without_calling_any_tier(self):
        with patch("swarm.pii_classify.subprocess.run") as subp_mock, \
             patch("swarm.pii_classify._make_classifier_with_anthropic") as fake_t1:
            classifier = pc.default_classifier()
            self.assertEqual(classifier("hi"), [])  # 2 chars, well below 8-char floor
        subp_mock.assert_not_called()
        fake_t1.return_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
