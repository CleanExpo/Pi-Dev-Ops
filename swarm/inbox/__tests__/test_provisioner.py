"""Tests for swarm.inbox.provisioner (Hour-1 portal worker).

Mocks every external call (Supabase PostgREST, Linear GraphQL, Resend,
Telegram) so the suite never hits the network.
"""
from __future__ import annotations

import json
import os
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

os.environ.setdefault("SUPABASE_UNITE_GROUP_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_UNITE_GROUP_SERVICE_KEY", "test-key")
os.environ.setdefault("LINEAR_API_KEY", "lin_test")
os.environ.setdefault("RESEND_API_KEY", "re_test")

from swarm.inbox import provisioner as P  # noqa: E402


def _queue_row(**overrides):
    base = dict(
        id="row-1",
        stripe_customer_id="cus_test",
        nexus_slug="dimitri-itr",
        trigger="checkout.session.completed",
        trigger_payload={"session_id": "cs_test"},
        status="pending",
    )
    base.update(overrides)
    return base


def _client(**overrides):
    base = dict(
        id="client-1",
        slug="dimitri-itr",
        company_name="Duncan Perkins Home Loan Essentials",
        contact_name="Duncan Perkins",
        contact_email="Duncan@homeloanessentials.com.au",
        plan=None,
        status="active",
        brand_config={"candidates": [
            {"name": "Lodgey", "tagline": "Lodge the file", "tm_status": "primary"},
            {"name": "BeauHQ", "tagline": "Clean compound", "tm_status": "backup"},
        ]},
        portal_content={},
    )
    base.update(overrides)
    return base


def _http_error(code, msg='err'):
    import io
    return urllib.error.HTTPError(url='x', code=code, msg=msg, hdrs=None, fp=io.BytesIO(b''))


class BuildDay0PortalContentTests(unittest.TestCase):
    def test_includes_all_six_sections(self):
        client = _client()
        linear = {"id": "lin-1", "url": "https://linear.app/x"}
        out = P.build_day0_portal_content(
            client=client, linear_project=linear,
            brand_candidates=client["brand_config"]["candidates"],
        )
        for key in ("engagement", "brand_vote", "build_stream",
                    "preview_deploys", "approvals_queue", "compliance_vault"):
            self.assertIn(key, out)

    def test_brand_vote_active_with_zero_tallies(self):
        client = _client()
        out = P.build_day0_portal_content(
            client=client, linear_project=None,
            brand_candidates=client["brand_config"]["candidates"],
        )
        self.assertTrue(out["brand_vote"]["active"])
        self.assertEqual(out["brand_vote"]["votes"]["Lodgey"], 0)
        self.assertEqual(out["brand_vote"]["votes"]["BeauHQ"], 0)

    def test_preserves_existing_portal_content_keys(self):
        client = _client(portal_content={"existing_key": "kept"})
        out = P.build_day0_portal_content(
            client=client, linear_project=None,
            brand_candidates=client["brand_config"]["candidates"],
        )
        self.assertEqual(out["existing_key"], "kept")

    def test_approvals_queue_has_discovery_blocker(self):
        client = _client()
        out = P.build_day0_portal_content(
            client=client, linear_project=None,
            brand_candidates=client["brand_config"]["candidates"],
        )
        items = out["approvals_queue"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "discovery-day0")
        self.assertTrue(items[0]["blocking"])


class ResolveBrandCandidatesTests(unittest.TestCase):
    def test_uses_brand_config_dicts(self):
        client = _client()
        cands = P.resolve_brand_candidates(client)
        self.assertEqual(len(cands), 2)
        self.assertEqual(cands[0]["name"], "Lodgey")

    def test_wraps_raw_strings(self):
        client = _client(brand_config={"candidates": ["Foo", "Bar"]})
        cands = P.resolve_brand_candidates(client)
        self.assertEqual(cands[0], {"name": "Foo", "tagline": "", "tm_status": "candidate"})

    def test_fallback_when_missing(self):
        client = _client(brand_config={})
        cands = P.resolve_brand_candidates(client)
        self.assertEqual(len(cands), 2)
        self.assertEqual(cands[0]["name"], "Option A")


class ProvisionOneTests(unittest.TestCase):
    def test_happy_path_creates_linear_project_writes_day0_sends_email_and_pings(self):
        row = _queue_row()
        client = _client()
        sb_calls = []

        def fake_sb(method, path, **kw):
            sb_calls.append((method, path, kw.get("body")))
            if method == "GET" and "/nexus_clients" in path:
                return [client]
            return None

        with patch.object(P, "_sb_request", side_effect=fake_sb) as sb_mock, \
             patch.object(P, "create_linear_project",
                          return_value={"id": "lin-1", "url": "https://linear.app/x", "name": "X"}) as linear_mock, \
             patch.object(P, "_send_email") as email_mock, \
             patch.object(P, "_telegram_ping") as tg_mock:
            outcome = P._provision_one(row, dry_run=False)

        self.assertEqual(outcome, "done")
        linear_mock.assert_called_once()
        email_mock.assert_called_once()
        tg_mock.assert_called_once()
        # Day-0 PATCH happened with portal_content
        patches = [c for c in sb_calls if c[0] == "PATCH" and "/nexus_clients" in c[1]]
        self.assertEqual(len(patches), 1)
        self.assertIn("engagement", patches[0][2]["portal_content"])
        self.assertIn("brand_vote", patches[0][2]["portal_content"])
        # ContextBot enqueued
        ctxbot_inserts = [c for c in sb_calls if c[0] == "POST" and "/context_bots" in c[1]]
        self.assertEqual(len(ctxbot_inserts), 1)
        self.assertEqual(ctxbot_inserts[0][2]["provision_status"], "pending")

    def test_skips_linear_create_if_project_already_exists(self):
        row = _queue_row()
        client = _client(portal_content={
            "linear_project_id": "existing-lin",
            "linear_project_url": "https://linear.app/existing",
        })

        def fake_sb(method, path, **kw):
            if method == "GET" and "/nexus_clients" in path:
                return [client]
            return None

        with patch.object(P, "_sb_request", side_effect=fake_sb), \
             patch.object(P, "create_linear_project") as linear_mock, \
             patch.object(P, "_send_email"), \
             patch.object(P, "_telegram_ping"):
            P._provision_one(row, dry_run=False)
        linear_mock.assert_not_called()

    def test_context_bot_409_conflict_is_swallowed(self):
        row = _queue_row()
        client = _client()
        sb_seq = []

        def fake_sb(method, path, **kw):
            sb_seq.append((method, path))
            if method == "GET" and "/nexus_clients" in path:
                return [client]
            if method == "POST" and "/context_bots" in path:
                raise _http_error(409)
            return None

        with patch.object(P, "_sb_request", side_effect=fake_sb), \
             patch.object(P, "create_linear_project",
                          return_value={"id": "lin-1", "url": "https://linear.app/x", "name": "X"}), \
             patch.object(P, "_send_email"), \
             patch.object(P, "_telegram_ping"):
            outcome = P._provision_one(row, dry_run=False)
        self.assertEqual(outcome, "done")

    def test_dry_run_makes_no_external_writes(self):
        row = _queue_row()
        client = _client()
        sb_calls = []

        def fake_sb(method, path, **kw):
            sb_calls.append((method, path))
            if method == "GET" and "/nexus_clients" in path:
                return [client]
            return None

        with patch.object(P, "_sb_request", side_effect=fake_sb), \
             patch.object(P, "create_linear_project") as linear_mock, \
             patch.object(P, "_send_email") as email_mock, \
             patch.object(P, "_telegram_ping") as tg_mock:
            outcome = P._provision_one(row, dry_run=True)
        self.assertEqual(outcome, "done")
        linear_mock.assert_not_called()
        email_mock.assert_not_called()
        tg_mock.assert_not_called()
        # The only sb_request should be the initial nexus_clients GET
        non_get = [c for c in sb_calls if c[0] != "GET"]
        self.assertEqual(non_get, [])

    def test_missing_client_raises(self):
        row = _queue_row(nexus_slug="nonexistent")
        with patch.object(P, "_sb_request", return_value=[]):
            with self.assertRaises(RuntimeError):
                P._provision_one(row, dry_run=False)


class TickTests(unittest.TestCase):
    def test_processes_pending_rows_and_marks_done(self):
        rows = [_queue_row(id="r1"), _queue_row(id="r2", nexus_slug="other")]
        patches = []

        def fake_sb(method, path, **kw):
            if method == "GET" and "/stripe_provisioning_queue" in path:
                return rows
            if method == "PATCH" and "/stripe_provisioning_queue" in path:
                patches.append(kw.get("body"))
            return None

        with patch.object(P, "_sb_request", side_effect=fake_sb), \
             patch.object(P, "_provision_one", return_value="done"):
            result = P.tick(dry_run=False)
        self.assertEqual(result["rows_seen"], 2)
        self.assertEqual(result["processed"], 2)
        # Each row gets 2 PATCH calls: processing + done
        self.assertEqual(len(patches), 4)
        self.assertEqual(patches[0]["status"], "processing")
        self.assertEqual(patches[1]["status"], "done")

    def test_failure_marks_row_failed_and_continues(self):
        rows = [_queue_row(id="bad"), _queue_row(id="good")]
        patches = []

        def fake_sb(method, path, **kw):
            if method == "GET" and "/stripe_provisioning_queue" in path:
                return rows
            if method == "PATCH" and "/stripe_provisioning_queue" in path:
                patches.append(kw.get("body"))
            return None

        def fake_provision(row, dry_run):
            if row["id"] == "bad":
                raise RuntimeError("boom")
            return "done"

        with patch.object(P, "_sb_request", side_effect=fake_sb), \
             patch.object(P, "_provision_one", side_effect=fake_provision):
            result = P.tick(dry_run=False)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(len(result["failed"]), 1)
        self.assertIn("bad", result["failed"][0])
        # The bad row got: processing, failed (with error). The good row: processing, done.
        statuses = [p["status"] for p in patches]
        self.assertIn("failed", statuses)
        self.assertIn("done", statuses)

    def test_no_pending_rows_is_clean_noop(self):
        with patch.object(P, "_sb_request", return_value=[]):
            result = P.tick(dry_run=False)
        self.assertEqual(result["rows_seen"], 0)
        self.assertEqual(result["processed"], 0)


if __name__ == "__main__":
    unittest.main()
