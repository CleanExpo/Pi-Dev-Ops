"""Tests for swarm.inbox.intake_router.

Mocks urllib.request.urlopen so the suite never hits the live Supabase
or Telegram APIs. Verifies routing, dedupe, wiki append, Linear filing,
authorization, and tick() loop behaviour.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

# Env vars are required by the router at import time when calling
# _supabase_*().  Set safe defaults before import.
os.environ.setdefault("SUPABASE_UNITE_GROUP_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")

from swarm.inbox import intake_router as ir  # noqa: E402


def _http_response(payload, status=200):
    """Build a fake context-manager response for urlopen."""
    body = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else payload
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code, body_bytes=b""):
    err = urllib.error.HTTPError(
        url="x", code=code, msg="err", hdrs=None,
        fp=io.BytesIO(body_bytes),
    )
    return err


def _bot(**overrides):
    base = dict(
        id="bot-1",
        bot_username="PiCeoUniteGroupBot",
        bot_token="tok",
        kind="portfolio",
        brand="pi-ceo",
        context_id="unite-group",
        context_label="Unite-Group",
        linear_team_key="UNI",
        linear_project_id=None,
        wiki_section=None,
        greeting_template="Filed.",
        auto_reply_enabled=True,
        long_poll_offset=0,
        authorized_chat_ids=[],
    )
    base.update(overrides)
    return ir.Bot(**base)


def _update(update_id=1, text="hello", user_id=42, message_id=1, chat_id=42):
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": user_id, "username": "phill"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1715645000,
            "text": text,
        },
    }


class LoadRegistryTests(unittest.TestCase):
    def test_load_registry_only_returns_intake_enabled(self):
        rows = [
            {"id": "a", "bot_username": "InBot", "bot_token": "t", "kind": "portfolio",
             "brand": "pi-ceo", "context_id": "x", "context_label": "X",
             "linear_team_key": "UNI", "linear_project_id": None, "wiki_section": None,
             "greeting_template": None, "auto_reply_enabled": True,
             "long_poll_offset": 5, "authorized_chat_ids": []},
        ]
        with patch("urllib.request.urlopen", return_value=_http_response(rows)) as mock_open:
            bots = ir.load_registry()
        # PostgREST URL should include intake_enabled=eq.true
        called_url = mock_open.call_args[0][0].full_url
        self.assertIn("intake_enabled=eq.true", called_url)
        self.assertEqual(len(bots), 1)
        self.assertEqual(bots[0].long_poll_offset, 5)


class PollBotTests(unittest.TestCase):
    def test_poll_uses_offset(self):
        bot = _bot(long_poll_offset=42)
        with patch("urllib.request.urlopen", return_value=_http_response({"ok": True, "result": []})) as mock_open:
            ir.poll_bot(bot)
        req = mock_open.call_args[0][0]
        body = req.data.decode()
        self.assertIn("offset=42", body)
        self.assertIn("getUpdates", req.full_url)


class ProcessUpdateTests(unittest.TestCase):
    def setUp(self):
        self.wiki_root = Path(tempfile.mkdtemp())
        self._patch_wiki = patch.object(ir, "WIKI_ROOT", self.wiki_root)
        self._patch_wiki.start()

    def tearDown(self):
        self._patch_wiki.stop()

    def test_files_to_linear_and_wiki_on_normal_message(self):
        bot = _bot()
        linear_mock = MagicMock(return_value={"identifier": "UNI-9999"})
        with patch.object(ir, "_sb_request") as sb, \
             patch.object(ir, "_send_reply") as reply, \
             patch.dict(
                 "sys.modules",
                 {"swarm.linear_tools": MagicMock(save_issue=linear_mock)},
             ):
            n, lid = ir._process_update(bot, _update(text="add a new floor plan widget"), dry_run=False)
        self.assertEqual(n, 1)
        self.assertEqual(lid, "UNI-9999")
        linear_mock.assert_called_once()
        # Wiki file was created
        contexts = list(self.wiki_root.rglob("*.md"))
        self.assertEqual(len(contexts), 1)
        self.assertIn("add a new floor plan widget", contexts[0].read_text())
        # Auto-reply was sent
        reply.assert_called_once()

    def test_dedupes_on_409(self):
        bot = _bot()
        # _sb_request raises 409 on the messages insert
        def fake_sb(method, path, **kw):
            if path == "/context_bot_messages" and method == "POST":
                raise _http_error(409, b'{"code":"23505"}')
            return None
        with patch.object(ir, "_sb_request", side_effect=fake_sb), \
             patch.object(ir, "_send_reply") as reply, \
             patch.dict(
                 "sys.modules",
                 {"swarm.linear_tools": MagicMock(save_issue=MagicMock(return_value={"identifier":"UNI-1"}))},
             ):
            n, _ = ir._process_update(bot, _update(), dry_run=False)
        self.assertEqual(n, 0)
        # Auto-reply must NOT fire on a duplicate
        reply.assert_not_called()

    def test_unauthorized_user_rejected(self):
        bot = _bot(authorized_chat_ids=[111])  # 42 not in list
        with patch.object(ir, "_sb_request") as sb, \
             patch.object(ir, "_send_reply") as reply:
            n, _ = ir._process_update(bot, _update(user_id=42), dry_run=False)
        self.assertEqual(n, 0)
        sb.assert_not_called()
        reply.assert_not_called()

    def test_non_message_update_noop(self):
        bot = _bot()
        non_msg = {"update_id": 5}  # no "message" key
        with patch.object(ir, "_sb_request") as sb:
            n, _ = ir._process_update(bot, non_msg, dry_run=False)
        self.assertEqual(n, 0)
        sb.assert_not_called()

    def test_dry_run_makes_no_external_writes(self):
        bot = _bot()
        with patch.object(ir, "_sb_request") as sb, \
             patch.object(ir, "_send_reply") as reply:
            n, lid = ir._process_update(bot, _update(text="hi"), dry_run=True)
        self.assertEqual(n, 1)
        self.assertIsNone(lid)
        sb.assert_not_called()
        reply.assert_not_called()
        # No wiki file written in dry-run
        self.assertEqual(list(self.wiki_root.rglob("*.md")), [])

    def test_reply_includes_linear_issue_id(self):
        bot = _bot(greeting_template="Got it.")
        captured = {}
        def fake_reply(b, chat_id, text):
            captured["text"] = text
        linear_mock = MagicMock(return_value={"identifier": "UNI-4242"})
        with patch.object(ir, "_sb_request"), \
             patch.object(ir, "_send_reply", side_effect=fake_reply), \
             patch.dict("sys.modules", {"swarm.linear_tools": MagicMock(save_issue=linear_mock)}):
            ir._process_update(bot, _update(), dry_run=False)
        self.assertIn("UNI-4242", captured["text"])
        self.assertIn("Got it.", captured["text"])


class TickTests(unittest.TestCase):
    def test_tick_advances_offset_to_max_plus_one(self):
        bot = _bot(long_poll_offset=10)
        updates = [_update(update_id=11), _update(update_id=13)]
        offset_calls = []

        def fake_sb(method, path, **kw):
            if path == "/context_bots" and method == "PATCH":
                offset_calls.append((kw.get("params"), kw.get("body")))
                return None
            return None

        with patch.object(ir, "load_registry", return_value=[bot]), \
             patch.object(ir, "poll_bot", return_value=updates), \
             patch.object(ir, "_process_update", return_value=(1, "UNI-1")), \
             patch.object(ir, "_sb_request", side_effect=fake_sb):
            result = ir.tick(dry_run=False)
        self.assertEqual(result["bots_polled"], 1)
        self.assertEqual(result["messages_filed"], 2)
        self.assertEqual(len(offset_calls), 1)
        self.assertEqual(offset_calls[0][1]["long_poll_offset"], 14)

    def test_tick_continues_on_per_bot_poll_failure(self):
        good = _bot(id="b1", bot_username="Good")
        bad = _bot(id="b2", bot_username="Bad")

        def fake_poll(bot):
            if bot.bot_username == "Bad":
                raise RuntimeError("boom")
            return [_update(update_id=99)]

        with patch.object(ir, "load_registry", return_value=[bad, good]), \
             patch.object(ir, "poll_bot", side_effect=fake_poll), \
             patch.object(ir, "_process_update", return_value=(1, "UNI-1")), \
             patch.object(ir, "_sb_request"):
            result = ir.tick(dry_run=False)
        # Bad recorded as error; Good still processed → messages_filed >= 1
        self.assertGreaterEqual(result["messages_filed"], 1)
        self.assertTrue(any("Bad" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
