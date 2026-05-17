"""Tests for swarm.inbox.botfather_minter.

Mocks urllib.request.urlopen (for the Supabase insert) and `_open_client`
(for Telethon) so the suite NEVER hits the network or my.telegram.org.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

# The minter reads SUPABASE_UNITE_GROUP_* on insert. Set safe defaults
# before import so `_supabase_*()` doesn't KeyError if exercised.
os.environ.setdefault("SUPABASE_UNITE_GROUP_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")

from swarm.inbox import botfather_minter as bm  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────
def _http_response(payload, status=200):
    body = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else payload
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code, body_bytes=b""):
    return urllib.error.HTTPError(
        url="x", code=code, msg="err", hdrs=None,
        fp=io.BytesIO(body_bytes),
    )


def _seed_queue(tmp: Path, *, status: str = "pending", n: int = 2,
                custom: list[dict] | None = None) -> Path:
    """Write a fresh queue to `tmp / 'q.jsonl'`."""
    items: list[dict]
    if custom is not None:
        items = custom
    else:
        items = []
        for i in range(n):
            items.append({
                "context_id": f"ctx-{i}",
                "bot_username": f"TestBot{i}Bot",
                "display_name": f"Test Bot {i}",
                "kind": "portfolio",
                "brand": "pi-ceo",
                "intake_enabled": True,
                "auto_reply_enabled": True,
                "wiki_section": None,
                "linear_team_key": None,
                "linear_project_id": None,
                "authorized_chat_ids": [],
                "client_email": None,
                "client_display_name": None,
                "status": status,
                "minted_at": None,
                "token": None,
                "reason": None,
            })
    path = tmp / "q.jsonl"
    path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    return path


# ── Tests ──────────────────────────────────────────────────────────────────
class QueueSeedTests(unittest.TestCase):
    def test_queue_seed_loads(self):
        """The shipped seed file at .harness/swarm/botfather_queue.jsonl
        must load cleanly as exactly 8 pending lines, in mint order."""
        items = bm.load_queue(bm.DEFAULT_QUEUE_PATH)
        self.assertEqual(len(items), 8, "seed queue must have 8 lines")
        self.assertTrue(all(it["status"] == "pending" for it in items),
                        "every seed line must be pending")
        usernames = [it["bot_username"] for it in items]
        self.assertEqual(usernames, [
            "PiCeoRestoreAssistBot", "PiCeoDRBot", "PiCeoNRPGBot",
            "PiCeoCARSIBot", "PiCeoATIABot",
            "UniteGroupCCWBot", "UniteGroupDuncanBot", "UniteGroupIviBot",
        ])

    def test_load_queue_handles_malformed_jsonl_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "q.jsonl"
            p.write_text(
                '{"context_id":"ok","status":"pending"}\n'
                'not-json-at-all\n'
                '{"context_id":"ok2","status":"pending"}\n'
                '\n'   # blank line — must be skipped silently
                '{"missing closing brace\n'
            )
            items = bm.load_queue(p)
        # Only the 2 valid JSON objects survive
        self.assertEqual(len(items), 2)
        self.assertEqual({it["context_id"] for it in items}, {"ok", "ok2"})


class DryRunTests(unittest.TestCase):
    def test_dry_run_calls_no_send(self):
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), n=3)
            # _open_client MUST NOT be called in dry-run.
            with patch.object(bm, "_open_client") as oc, \
                 patch.object(bm, "_sb_request") as sb, \
                 patch.object(bm, "_mint_one") as mo:
                result = bm.mint_queue(dry_run=True, queue_path=q)
            oc.assert_not_called()
            sb.assert_not_called()
            mo.assert_not_called()
            self.assertEqual(result["minted"], 0)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["pending"], 3,
                             "dry-run must NOT mutate persisted status")


class RateLimitTests(unittest.TestCase):
    def test_rate_limit_parses_seconds_and_sleeps(self):
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), n=1)
            sleep_calls: list[float] = []
            # _mint_one: first call returns rate-limit:30, second call mints.
            seq = iter([
                ("rate_limited:30", None, "Too many attempts. Please try again in 30 seconds."),
                ("minted", "1234:TOKEN_AAAA", None),
            ])
            with patch.object(bm, "_open_client", return_value=MagicMock()), \
                 patch.object(bm, "_sb_request"), \
                 patch.object(bm, "_mint_one", side_effect=lambda c, l: next(seq)), \
                 patch.object(bm.time, "sleep", side_effect=sleep_calls.append):
                result = bm.mint_queue(dry_run=False, queue_path=q,
                                        max_wait_seconds=120)
            self.assertEqual(result["minted"], 1)
            # First sleep is the rate-limit wait (30 + 5 safety pad).
            self.assertIn(35, sleep_calls)
            # No rate_limited_until recorded — wait was within budget.
            self.assertIsNone(result["rate_limited_until"])

    def test_rate_limit_exceeds_budget_returns_early(self):
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), n=2)
            # 7200s wait blows the 1800s budget → early return, line stays pending.
            with patch.object(bm, "_open_client", return_value=MagicMock()), \
                 patch.object(bm, "_sb_request") as sb, \
                 patch.object(bm, "_mint_one",
                              return_value=("rate_limited:7200", None, "wait 2 hours")), \
                 patch.object(bm.time, "sleep"), \
                 patch.object(bm, "_write_state") as ws:
                result = bm.mint_queue(dry_run=False, queue_path=q,
                                        max_wait_seconds=1800)
            self.assertEqual(result["minted"], 0)
            self.assertIsNotNone(result["rate_limited_until"])
            ws.assert_called_once()
            sb.assert_not_called()
            # First line still pending so the next LaunchAgent run resumes it.
            items = bm.load_queue(q)
            self.assertEqual(items[0]["status"], "pending")


class UsernameTakenTests(unittest.TestCase):
    def test_username_taken_marks_failed_continues(self):
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), n=2)
            seq = iter([
                ("username_taken", None, "Sorry, this username is already taken."),
                ("minted", "1234:TOKEN_BBBB", None),
            ])
            with patch.object(bm, "_open_client", return_value=MagicMock()), \
                 patch.object(bm, "_sb_request") as sb, \
                 patch.object(bm, "_mint_one", side_effect=lambda c, l: next(seq)), \
                 patch.object(bm.time, "sleep"):
                result = bm.mint_queue(dry_run=False, queue_path=q)
            # First → failed, second → minted, run continues.
            self.assertEqual(result["minted"], 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("username taken", result["errors"][0])
            items = bm.load_queue(q)
            self.assertEqual(items[0]["status"], "failed")
            self.assertIn("username_taken", items[0]["reason"])
            self.assertEqual(items[1]["status"], "minted")
            # Only ONE Supabase insert (the successful one).
            self.assertEqual(sb.call_count, 1)


class SupabaseInsertTests(unittest.TestCase):
    def test_successful_mint_inserts_into_supabase(self):
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), custom=[{
                "context_id": "ccw", "bot_username": "UniteGroupCCWBot",
                "display_name": "Carpet Cleaners Warehouse",
                "kind": "client", "brand": "unite-group",
                "intake_enabled": True, "auto_reply_enabled": True,
                "wiki_section": None,
                "linear_team_key": None, "linear_project_id": None,
                "authorized_chat_ids": [],
                "client_email": "toby@example.com",
                "client_display_name": "Toby Carstairs",
                "status": "pending", "minted_at": None, "token": None,
                "reason": None,
            }])
            captured: dict = {}

            def fake_sb(method, path, **kw):
                captured["method"] = method
                captured["path"] = path
                captured["body"] = kw.get("body")
                captured["headers"] = kw.get("extra_headers")
                return None

            with patch.object(bm, "_open_client", return_value=MagicMock()), \
                 patch.object(bm, "_sb_request", side_effect=fake_sb), \
                 patch.object(bm, "_mint_one",
                              return_value=("minted", "9999:TOKEN_XYZ", None)), \
                 patch.object(bm.time, "sleep"):
                result = bm.mint_queue(dry_run=False, queue_path=q)

            self.assertEqual(result["minted"], 1)
            self.assertEqual(captured["method"], "POST")
            self.assertEqual(captured["path"], "/context_bots")
            body = captured["body"]
            self.assertEqual(body["bot_username"], "UniteGroupCCWBot")
            self.assertEqual(body["bot_token"], "9999:TOKEN_XYZ")
            self.assertEqual(body["context_id"], "ccw")
            self.assertEqual(body["kind"], "client")
            self.assertEqual(body["brand"], "unite-group")
            self.assertEqual(body["client_email"], "toby@example.com")
            self.assertTrue(body["intake_enabled"])
            self.assertEqual(body["provision_status"], "live")
            self.assertEqual(captured["headers"], {"Prefer": "return=minimal"})


class PersistenceTests(unittest.TestCase):
    def test_persistence_atomic(self):
        """Mid-write SIGKILL must not corrupt the queue file. We simulate this
        by making `os.replace` raise after the tempfile is written — the
        original file must be untouched and still parse cleanly."""
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), n=2)
            original_contents = q.read_text()

            real_replace = os.replace

            def boom_replace(src, dst):
                # Simulate the process dying right before the atomic swap.
                # The original `dst` must still be intact.
                raise OSError("simulated SIGKILL mid-write")

            with patch.object(bm.os, "replace", side_effect=boom_replace):
                with self.assertRaises(OSError):
                    bm._atomic_write_queue([{"context_id": "x", "status": "pending"}], q)

            # The original file must be byte-identical (no partial write).
            self.assertEqual(q.read_text(), original_contents)
            # And still parse cleanly into the original 2 lines.
            items = bm.load_queue(q)
            self.assertEqual(len(items), 2)

            # Tempfile cleanup happened — no .botfather_queue.* lingering.
            stragglers = [p for p in Path(td).iterdir()
                          if p.name.startswith(".botfather_queue.")]
            self.assertEqual(stragglers, [], f"tempfile not cleaned: {stragglers}")

            # Sanity: a normal write with the real os.replace still works.
            real_replace  # noqa: B018 — referenced to satisfy linter
            bm._atomic_write_queue([{"context_id": "x", "status": "pending"}], q)
            items = bm.load_queue(q)
            self.assertEqual(items[0]["context_id"], "x")


class ResumeTests(unittest.TestCase):
    def test_resume_skips_already_minted(self):
        """A queue with some lines already status=minted must skip them and
        only mint the remaining pending lines."""
        with tempfile.TemporaryDirectory() as td:
            q = _seed_queue(Path(td), custom=[
                {"context_id": "a", "bot_username": "ABot",
                 "display_name": "A", "kind": "portfolio", "brand": "pi-ceo",
                 "intake_enabled": True, "auto_reply_enabled": True,
                 "wiki_section": None, "linear_team_key": None,
                 "linear_project_id": None, "authorized_chat_ids": [],
                 "client_email": None, "client_display_name": None,
                 "status": "minted", "minted_at": "2026-05-14T10:00:00+10:00",
                 "token": "1:OLD", "reason": None},
                {"context_id": "b", "bot_username": "BBot",
                 "display_name": "B", "kind": "portfolio", "brand": "pi-ceo",
                 "intake_enabled": True, "auto_reply_enabled": True,
                 "wiki_section": None, "linear_team_key": None,
                 "linear_project_id": None, "authorized_chat_ids": [],
                 "client_email": None, "client_display_name": None,
                 "status": "pending", "minted_at": None, "token": None,
                 "reason": None},
            ])
            mint_calls: list = []

            def fake_mint(client, line):
                mint_calls.append(line["bot_username"])
                return ("minted", "2:NEW", None)

            with patch.object(bm, "_open_client", return_value=MagicMock()), \
                 patch.object(bm, "_sb_request"), \
                 patch.object(bm, "_mint_one", side_effect=fake_mint), \
                 patch.object(bm.time, "sleep"):
                result = bm.mint_queue(dry_run=False, queue_path=q)
            self.assertEqual(mint_calls, ["BBot"], "must only mint pending")
            self.assertEqual(result["minted"], 1)
            items = bm.load_queue(q)
            # Already-minted line is untouched.
            self.assertEqual(items[0]["token"], "1:OLD")
            self.assertEqual(items[1]["token"], "2:NEW")


class RateLimitParseTests(unittest.TestCase):
    def test_parse_rate_limit_seconds_handles_units(self):
        self.assertEqual(
            bm._parse_rate_limit_seconds("Too many attempts. Please try again in 30 seconds."),
            30,
        )
        self.assertEqual(
            bm._parse_rate_limit_seconds("Too many attempts. Please try again in 5 minutes."),
            300,
        )
        self.assertEqual(
            bm._parse_rate_limit_seconds("Too many attempts. Please try again in 2 hours."),
            7200,
        )
        # Non-rate-limit text returns None.
        self.assertIsNone(
            bm._parse_rate_limit_seconds("Done! Congratulations on your new bot."),
        )


if __name__ == "__main__":
    unittest.main()
