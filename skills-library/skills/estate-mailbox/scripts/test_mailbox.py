#!/usr/bin/env python3
"""Controls for the cross-node mailbox.

The mailbox is the only channel that reaches every node, so its failure modes are
estate-wide. The one that matters most is not "a message was lost" — it is "a message
was lost SILENTLY", or "one corrupt line made every later message unreadable". Both
look like an empty inbox, which is what a working quiet system also looks like.

    python3 test_mailbox.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mailbox  # noqa: E402


class MailboxCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mailbox-test-")
        self._real = mailbox.MAILDIR
        mailbox.MAILDIR = os.path.join(self.tmp, "mailbox")
        os.makedirs(mailbox.MAILDIR, exist_ok=True)

    def tearDown(self):
        mailbox.MAILDIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_raw(self, node, text):
        with open(os.path.join(mailbox.MAILDIR, f"{node}.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(text)


class RoundTrip(MailboxCase):
    def test_a_posted_message_is_read_back(self):
        mailbox.post("mini", "review-request", "body text", ref="abc123", frm="cloud")
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(problems, [])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["from"], "cloud")
        self.assertEqual(msgs[0]["ref"], "abc123")
        self.assertEqual(msgs[0]["body"], "body text")

    def test_an_empty_mailbox_is_not_an_error(self):
        msgs, problems = mailbox.read_mailbox("windows")
        self.assertEqual((msgs, problems), ([], []))

    def test_ids_are_unique_across_identical_messages(self):
        a = mailbox.post("mini", "note", "same", frm="cloud")
        b = mailbox.post("mini", "note", "same", frm="cloud")
        self.assertNotEqual(a["id"], b["id"], "identical bodies collided; ack would hit both")


class Corruption(MailboxCase):
    """One bad append must not cost every message after it."""

    def test_a_truncated_line_is_reported_and_skipped(self):
        # A process killed mid-write leaves exactly this.
        self.write_raw("mini", '{"id":"x","ts":"t","from":"a","kind":"note","body":"hal\n')
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(msgs, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("unparseable", problems[0])
        self.assertIn(":1:", problems[0], "problem must name the line number")

    def test_messages_after_a_corrupt_line_are_still_delivered(self):
        # THE property. Without it, one bad append silently orphans the rest of the
        # file, and an inbox with lost mail is indistinguishable from a quiet one.
        self.write_raw("mini", 'garbage not json\n')
        mailbox.post("mini", "note", "must survive", frm="macbook")
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(len(msgs), 1, "a later message was lost behind a corrupt line")
        self.assertEqual(msgs[0]["body"], "must survive")
        self.assertEqual(len(problems), 1)

    def test_git_conflict_markers_are_named_as_such(self):
        # Two nodes appending in the same sync window produce these. "Unparseable JSON"
        # would send someone hunting a bug instead of resolving a merge.
        self.write_raw("mini", "<<<<<<< HEAD\n=======\n>>>>>>> theirs\n")
        _, problems = mailbox.read_mailbox("mini")
        self.assertEqual(len(problems), 3)
        for p in problems:
            self.assertIn("conflict marker", p)

    def test_a_message_missing_required_fields_is_skipped_not_returned_half_built(self):
        self.write_raw("mini", json.dumps({"from": "a", "body": "no id or ts"}) + "\n")
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(msgs, [])
        self.assertIn("missing", problems[0])

    def test_a_json_scalar_is_not_mistaken_for_a_message(self):
        self.write_raw("mini", '"just a string"\n42\n')
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(msgs, [])
        self.assertEqual(len(problems), 2)

    def test_blank_lines_are_not_problems(self):
        mailbox.post("mini", "note", "x", frm="cloud")
        self.write_raw("mini", "\n\n   \n")
        msgs, problems = mailbox.read_mailbox("mini")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(problems, [], "whitespace is not corruption")


class BodyIntegrity(MailboxCase):
    def test_a_multiline_body_stays_one_record(self):
        # A raw newline would split one message across several JSONL lines, and the
        # tail would then read as corruption. json.dumps escapes them.
        body = "line one\nline two\n\nline four"
        mailbox.post("mini", "verdict", body, frm="cloud")
        with open(os.path.join(mailbox.MAILDIR, "mini.jsonl"), encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 1, "body newlines split the record")
        msgs, _ = mailbox.read_mailbox("mini")
        self.assertEqual(msgs[0]["body"], body)

    def test_unicode_survives(self):
        mailbox.post("mini", "note", "café — naïve — 日本語", frm="cloud")
        msgs, _ = mailbox.read_mailbox("mini")
        self.assertEqual(msgs[0]["body"], "café — naïve — 日本語")

    def test_an_oversized_body_is_refused_at_post_time(self):
        # Refuse on write, not on read. The mailbox syncs to every machine every 15
        # minutes; a large artefact belongs behind a git ref, not inlined.
        with self.assertRaises(SystemExit):
            mailbox.post("mini", "note", "x" * (mailbox.MAX_BODY + 1), frm="cloud")


class Addressing(MailboxCase):
    def test_an_unknown_recipient_is_refused(self):
        # Otherwise estate/mailbox/mnii.jsonl is created and accepts messages forever
        # that no node reads -- delivery that looks successful and goes nowhere.
        with self.assertRaises(SystemExit):
            mailbox.post("mnii", "note", "typo", frm="cloud")

    def test_known_nodes_match_the_fleet_registry(self):
        # If fleet.py grows a node and this list does not, that node can be probed but
        # never written to, which is a partial membership nobody would notice.
        fleet_scripts = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..",
            "fleet-compute", "scripts")
        if not os.path.isdir(fleet_scripts):
            self.skipTest("fleet-compute not present in this checkout")
        sys.path.insert(0, os.path.abspath(fleet_scripts))
        import fleet  # noqa
        self.assertEqual(set(mailbox.KNOWN_NODES), set(fleet.NODES),
                         "mailbox recipients and fleet nodes have diverged")


class Acking(MailboxCase):
    def test_acked_messages_drop_out_of_unread(self):
        m = mailbox.post("mini", "note", "handle me", frm="cloud")
        self.assertTrue(mailbox.ack("mini", m["id"]))
        self.assertEqual(mailbox.read_mailbox("mini")[0], [])
        self.assertEqual(len(mailbox.read_mailbox("mini", include_acked=True)[0]), 1)

    def test_acking_is_idempotent(self):
        m = mailbox.post("mini", "note", "x", frm="cloud")
        mailbox.ack("mini", m["id"])
        self.assertTrue(mailbox.ack("mini", m["id"]), "replaying an ack must be harmless")

    def test_acking_an_unknown_id_reports_false(self):
        self.assertFalse(mailbox.ack("mini", "nosuchid"))

    def test_ack_preserves_unparseable_lines_rather_than_dropping_them(self):
        # ack rewrites the file. If it dropped what it could not parse, a corrupt line
        # would be silently deleted along with any evidence of what went wrong.
        self.write_raw("mini", "garbage\n")
        m = mailbox.post("mini", "note", "x", frm="cloud")
        mailbox.ack("mini", m["id"])
        with open(os.path.join(mailbox.MAILDIR, "mini.jsonl"), encoding="utf-8") as fh:
            self.assertIn("garbage", fh.read())

    def test_ack_does_not_touch_other_messages(self):
        a = mailbox.post("mini", "note", "a", frm="cloud")
        mailbox.post("mini", "note", "b", frm="cloud")
        mailbox.ack("mini", a["id"])
        left = mailbox.read_mailbox("mini")[0]
        self.assertEqual([m["body"] for m in left], ["b"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
