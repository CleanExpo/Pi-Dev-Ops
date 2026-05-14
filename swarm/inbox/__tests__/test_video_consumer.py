"""Tests for swarm.inbox.video_consumer — drains video_production_queue."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("SUPABASE_UNITE_GROUP_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")


def _reload(briefs_dir: Path):
    os.environ["TAO_VIDEO_BRIEFS_DIR"] = str(briefs_dir)
    import importlib
    from swarm.inbox import video_consumer as mod
    importlib.reload(mod)
    return mod


def _row(**overrides):
    base = {
        "id": "queue-1",
        "trigger": "pr-merge",
        "source_repo": "cleanexpo/dimitri-itr",
        "source_pr_number": 42,
        "source_pr_url": "https://github.com/cleanexpo/dimitri-itr/pull/42",
        "source_pr_title": "feat: ITR draft form",
        "source_linear_issue": "UNI-1234",
        "source_preview_url": "https://dimitri-itr-pr-42.vercel.app",
        "client_slug": "dimitri-itr",
        "brand_slug": "dimitri",
        "composition_type": "weekly-proof",
        "channel": "portal-embed",
        "duration_seconds": 90,
        "production_brief": {
            "job_id": "dimitri-itr-12345-pr42",
            "brand": "dimitri",
            "composition_type": "weekly-proof",
            "story_sentence": "feat: ITR draft form",
        },
        "created_at": "2026-05-14T00:00:00Z",
    }
    base.update(overrides)
    return base


class HappyPathTests(unittest.TestCase):
    def test_dispatches_one_row_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            row = _row()
            # Track calls to PATCH (claim + mark-ready)
            patch_calls = []

            def fake_sb(method, path, **kw):
                if method == "GET":
                    return [row]
                if method == "PATCH":
                    patch_calls.append({"body": kw.get("body"), "params": kw.get("params")})
                    # Simulate successful claim — return non-empty
                    return [row]
                return None

            with patch.object(mod, "_sb_request", side_effect=fake_sb), \
                 patch.object(mod, "_telegram_ping") as tg, \
                 patch.object(mod, "_record_trace") as trace:
                result = mod.tick(dry_run=False)

            self.assertEqual(result["rows_seen"], 1)
            self.assertEqual(result["dispatched"], 1)
            self.assertEqual(result["errors"], [])
            # PATCH called twice: claim + mark-ready
            self.assertEqual(len(patch_calls), 2)
            self.assertEqual(patch_calls[0]["body"]["status"], "dispatched")
            self.assertEqual(patch_calls[1]["body"]["current_phase"], "ready-for-render")
            # Brief file written
            brief_path = Path(tmp) / "dimitri-itr-12345-pr42.json"
            self.assertTrue(brief_path.exists())
            saved = json.loads(brief_path.read_text())
            self.assertEqual(saved["job_id"], "dimitri-itr-12345-pr42")
            # Telegram + trace fired exactly once each
            tg.assert_called_once()
            trace.assert_called_once()

    def test_dry_run_makes_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            row = _row()
            sb_calls = []

            def fake_sb(method, path, **kw):
                sb_calls.append(method)
                if method == "GET":
                    return [row]
                return None

            with patch.object(mod, "_sb_request", side_effect=fake_sb), \
                 patch.object(mod, "_telegram_ping") as tg, \
                 patch.object(mod, "_record_trace") as trace:
                result = mod.tick(dry_run=True)

            self.assertEqual(result["dispatched"], 1)
            # Only the GET fetch should have happened — no PATCH writes
            self.assertEqual(sb_calls, ["GET"])
            tg.assert_not_called()
            trace.assert_not_called()
            # No brief file written
            self.assertEqual(list(Path(tmp).rglob("*.json")), [])


class FailureHandlingTests(unittest.TestCase):
    def test_claim_lost_to_another_consumer_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            row = _row()

            def fake_sb(method, path, **kw):
                if method == "GET":
                    return [row]
                if method == "PATCH":
                    # Simulate "another consumer beat us" — empty result
                    return []
                return None

            with patch.object(mod, "_sb_request", side_effect=fake_sb), \
                 patch.object(mod, "_telegram_ping"), \
                 patch.object(mod, "_record_trace"):
                result = mod.tick(dry_run=False)

            self.assertEqual(result["dispatched"], 0)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("another-consumer-already-claimed", result["errors"][0])

    def test_one_bad_row_does_not_block_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            good_row = _row(id="good")
            bad_row = _row(id="bad", production_brief=None)  # missing brief → KeyError

            def fake_sb(method, path, **kw):
                if method == "GET":
                    return [bad_row, good_row]
                return [good_row]  # all PATCHes succeed for the good row

            with patch.object(mod, "_sb_request", side_effect=fake_sb), \
                 patch.object(mod, "_telegram_ping"), \
                 patch.object(mod, "_record_trace"):
                result = mod.tick(dry_run=False)

            self.assertEqual(result["rows_seen"], 2)
            self.assertEqual(result["dispatched"], 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("bad", result["errors"][0])

    def test_no_pending_rows_is_clean_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            with patch.object(mod, "_sb_request", return_value=[]):
                result = mod.tick(dry_run=False)
            self.assertEqual(result["rows_seen"], 0)
            self.assertEqual(result["dispatched"], 0)
            self.assertEqual(result["errors"], [])


class TelegramHintTests(unittest.TestCase):
    def test_telegram_message_includes_claude_invocation_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _reload(Path(tmp))
            row = _row()
            captured = []

            def fake_tg(text):
                captured.append(text)

            with patch.object(mod, "_sb_request") as sb, \
                 patch.object(mod, "_telegram_ping", side_effect=fake_tg), \
                 patch.object(mod, "_record_trace"):
                sb.side_effect = lambda method, path, **kw: [row] if method == "GET" else [row]
                mod.tick(dry_run=False)

            self.assertEqual(len(captured), 1)
            msg = captured[0]
            # Sanity checks on the hint shape
            self.assertIn("dimitri-itr", msg)
            self.assertIn("weekly-proof", msg)
            self.assertIn("video-director", msg)
            self.assertIn("claude --print", msg)


if __name__ == "__main__":
    unittest.main()
