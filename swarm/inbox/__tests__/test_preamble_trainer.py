"""Tests for swarm.inbox.preamble_trainer."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("SUPABASE_UNITE_GROUP_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini")

from swarm.inbox import preamble_trainer as pt  # noqa: E402


class ListActiveContextsTests(unittest.TestCase):
    def test_aggregates_message_counts_and_joins_bot_metadata(self):
        # First call: messages with context_ids. Second call: bot metadata.
        message_rows = [
            {"context_id": "unite-group", "received_at": "2026-05-14T10:00:00", "id": "m1"},
            {"context_id": "unite-group", "received_at": "2026-05-14T10:05:00", "id": "m2"},
            {"context_id": "ccw", "received_at": "2026-05-14T11:00:00", "id": "m3"},
        ]
        bot_rows = [
            {"context_id": "unite-group", "context_label": "Unite-Group",
             "wiki_section": "unite-group.md"},
            {"context_id": "ccw", "context_label": "CCW", "wiki_section": "clients/ccw.md"},
        ]
        with patch.object(pt, "_sb_request", side_effect=[message_rows, bot_rows]):
            result = pt.list_active_contexts(window_hours=24)
        by_id = {c["context_id"]: c for c in result}
        self.assertEqual(by_id["unite-group"]["message_count"], 2)
        self.assertEqual(by_id["ccw"]["message_count"], 1)
        self.assertEqual(by_id["unite-group"]["context_label"], "Unite-Group")

    def test_no_messages_returns_empty(self):
        with patch.object(pt, "_sb_request", return_value=[]):
            self.assertEqual(pt.list_active_contexts(window_hours=24), [])


class BuildPromptTests(unittest.TestCase):
    def test_includes_messages_in_chronological_order(self):
        ctx = {"context_id": "x", "context_label": "X"}
        messages = [
            {"received_at": "2", "from_username": "u", "body": "second"},
            {"received_at": "1", "from_username": "u", "body": "first"},
        ]
        # fetch_messages returns desc; build_prompt reverses for chronological.
        prompt = pt.build_prompt(ctx, messages)
        i_first = prompt.index("first")
        i_second = prompt.index("second")
        self.assertLess(i_first, i_second)

    def test_prompt_contains_required_sections(self):
        ctx = {"context_id": "x", "context_label": "X"}
        messages = [{"received_at": "1", "from_username": "u", "body": "hi"}]
        prompt = pt.build_prompt(ctx, messages)
        for section in ("Vocabulary", "Recurring topics", "Communication style",
                        "Active commitments", "Red flags"):
            self.assertIn(section, prompt)


class WritePreambleTests(unittest.TestCase):
    def test_writes_with_frontmatter_and_returns_paths(self):
        ctx = {"context_id": "unite-group", "context_label": "Unite-Group"}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pt, "WIKI_ROOT", Path(tmp)):
                md_path, json_path = pt.write_preamble(ctx, "## Vocabulary\n- foo\n")
            content = Path(md_path).read_text()
        self.assertIn("context_id: unite-group", content)
        self.assertIn("context_label: Unite-Group", content)
        self.assertIn("schema_version: preamble-v2", content)
        self.assertIn("## Vocabulary", content)
        self.assertTrue(md_path.endswith("contexts/unite-group/preamble.md"))
        # Entities omitted → JSON sidecar should NOT be written
        self.assertIsNone(json_path)

    def test_writes_entities_json_when_provided(self):
        ctx = {"context_id": "unite-group", "context_label": "Unite-Group"}
        entities = {
            "people": [{"name": "Phill", "role": "CEO", "confirmed": True}],
            "decisions": [], "deadlines": [], "blockers": [], "commitments": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pt, "WIKI_ROOT", Path(tmp)):
                md_path, json_path = pt.write_preamble(ctx, "## Vocabulary\n", entities)
                payload = json.loads(Path(json_path).read_text())
        self.assertTrue(json_path.endswith("contexts/unite-group/preamble.json"))
        self.assertEqual(payload["schema_version"], "preamble-v2")
        self.assertEqual(payload["entities"]["people"][0]["name"], "Phill")


class SplitPreambleAndEntitiesTests(unittest.TestCase):
    def test_parses_fenced_json_and_strips_from_prose(self):
        response = (
            "## Vocabulary\n- foo\n\n"
            "```json\n"
            '{"people": [{"name": "Phill", "role": "CEO", "confirmed": true}],'
            ' "decisions": [], "deadlines": [], "blockers": [], "commitments": []}\n'
            "```\n"
        )
        body, entities = pt.split_preamble_and_entities(response)
        self.assertIn("## Vocabulary", body)
        self.assertNotIn("```json", body)
        self.assertEqual(entities["people"][0]["name"], "Phill")
        self.assertEqual(entities["decisions"], [])

    def test_no_fence_returns_full_text_and_canonical_empty(self):
        response = "## Vocabulary\n- foo (no JSON fence)\n"
        body, entities = pt.split_preamble_and_entities(response)
        self.assertIn("## Vocabulary", body)
        for k in ("people", "decisions", "deadlines", "blockers", "commitments"):
            self.assertEqual(entities[k], [])

    def test_invalid_json_falls_back_to_empty(self):
        response = (
            "## Vocabulary\n- foo\n\n"
            "```json\n{not valid json}\n```\n"
        )
        body, entities = pt.split_preamble_and_entities(response)
        # Prose preceding the bad fence is preserved
        self.assertIn("## Vocabulary", body)
        # Canonical empty keys
        for k in ("people", "decisions", "deadlines", "blockers", "commitments"):
            self.assertEqual(entities[k], [])

    def test_canonical_keys_added_when_gemini_omits_some(self):
        response = (
            "x\n```json\n"
            '{"people": [{"name": "Toby", "confirmed": true}]}\n'
            "```"
        )
        _, entities = pt.split_preamble_and_entities(response)
        # All 5 canonical keys present even though Gemini emitted only people
        self.assertEqual(entities["people"][0]["name"], "Toby")
        for k in ("decisions", "deadlines", "blockers", "commitments"):
            self.assertEqual(entities[k], [])


class TrainLoopTests(unittest.TestCase):
    def test_skips_empty_contexts(self):
        with patch.object(pt, "list_active_contexts", return_value=[
            {"context_id": "x", "context_label": "X", "wiki_section": None,
             "message_count": 0},
        ]), \
             patch.object(pt, "fetch_messages", return_value=[]), \
             patch.object(pt, "_gemini_summarise") as gem:
            r = pt.train(dry_run=False)
        gem.assert_not_called()
        self.assertEqual(r["preambles_written"], 0)

    def test_writes_for_each_active_context(self):
        contexts = [
            {"context_id": "ug", "context_label": "UG", "wiki_section": "ug.md", "message_count": 3},
            {"context_id": "ccw", "context_label": "CCW", "wiki_section": "ccw.md", "message_count": 5},
        ]
        msgs = [{"received_at": "t", "from_username": "u", "body": "hi"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pt, "list_active_contexts", return_value=contexts), \
                 patch.object(pt, "fetch_messages", return_value=msgs), \
                 patch.object(pt, "_gemini_summarise", return_value="## Vocabulary\n- foo"), \
                 patch.object(pt, "WIKI_ROOT", Path(tmp)):
                r = pt.train(dry_run=False)
            ug = Path(tmp) / "contexts/ug/preamble.md"
            ccw = Path(tmp) / "contexts/ccw/preamble.md"
            self.assertTrue(ug.exists())
            self.assertTrue(ccw.exists())
        self.assertEqual(r["preambles_written"], 2)

    def test_dry_run_calls_no_gemini_no_write(self):
        contexts = [{"context_id": "ug", "context_label": "UG", "wiki_section": None,
                     "message_count": 3}]
        msgs = [{"received_at": "t", "from_username": "u", "body": "hi"}]
        with patch.object(pt, "list_active_contexts", return_value=contexts), \
             patch.object(pt, "fetch_messages", return_value=msgs), \
             patch.object(pt, "_gemini_summarise") as gem, \
             patch.object(pt, "write_preamble") as wp:
            r = pt.train(dry_run=True)
        gem.assert_not_called()
        wp.assert_not_called()
        self.assertEqual(r["dry_run"], True)

    def test_continues_on_per_context_failure(self):
        contexts = [
            {"context_id": "ug", "context_label": "UG", "wiki_section": None, "message_count": 3},
            {"context_id": "ccw", "context_label": "CCW", "wiki_section": None, "message_count": 3},
        ]
        msgs = [{"received_at": "t", "from_username": "u", "body": "hi"}]
        def fake_gem(prompt, **kw):
            if "UG" in prompt:
                raise RuntimeError("boom")
            return "ok"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pt, "list_active_contexts", return_value=contexts), \
                 patch.object(pt, "fetch_messages", return_value=msgs), \
                 patch.object(pt, "_gemini_summarise", side_effect=fake_gem), \
                 patch.object(pt, "WIKI_ROOT", Path(tmp)):
                r = pt.train(dry_run=False)
        self.assertEqual(r["preambles_written"], 1)
        self.assertTrue(any("ug" in e for e in r["errors"]))


if __name__ == "__main__":
    unittest.main()
