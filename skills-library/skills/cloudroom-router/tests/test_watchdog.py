#!/usr/bin/env python3
"""Tests for scripts/watchdog.py. Run: python3 skills/cloudroom-router/tests/test_watchdog.py

The load-bearing cases are the UNKNOWN ones: a failed, empty or partial `room-cli` read must
exit 2 and say UNKNOWN. It must never look like "all clear".
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCHDOG = HERE.parent / "scripts" / "watchdog.py"
BOARD_PY = HERE.parent / "scripts" / "board.py"

NOW = 1_800_000_000_000
MIN = 60_000
ROUTER = "thr_router"

BOARD = """# Board

| id | slug | status | mode | runs | worker |
|----|------|--------|------|------|--------|
| 001 | done-one | done | solo | alongside | thr_old |
| 002 | running | doing | solo | alongside | thr_run |
| 003 | quiet | doing | solo | alongside | thr_quiet |
| 004 | finished | doing | solo | alongside | thr_fin |
| 005 | asking | doing | solo | alongside | thr_ask |
| 006 | lost | doing | solo | alongside | thr_gone |
| 007 | broke | doing | solo | alongside | thr_bad |
| 008 | queued | ready | solo | alongside | |
| 009 | parked | blocked (was doing) | solo | alongside | thr_parked |
"""


def thread(tid, status="idle", age_min=1, parent=ROUTER, pending=False, bg=0):
    return {"id": tid, "status": status, "parentThreadId": parent, "updatedAt": NOW - int(age_min * MIN),
            "hasPendingInteraction": pending, "activity": {"activeBackgroundCommandCount": bg},
            "runtime": {"displayStatus": status}}


def healthy():
    return [thread(ROUTER, "active", parent=None),
            thread("thr_run", "active", age_min=2),
            thread("thr_quiet", "active", age_min=45, bg=1),
            thread("thr_fin", "idle"),
            thread("thr_ask", "active", age_min=60, pending=True),
            thread("thr_bad", "error"),
            thread("thr_unrelated", "active", age_min=500, parent="thr_someone_else")]


class Setup(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="router-wd-"))
        self.tickets = self.dir / "tickets"
        self.set_board(BOARD)
        self.threads = self.dir / "threads.json"

    def set_board(self, table: str):
        """Build a tickets folder from a markdown table: each row becomes NNN-slug/ with a status file."""
        shutil.rmtree(self.tickets, ignore_errors=True)
        self.tickets.mkdir()
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table.splitlines()
                if re.match(r"^\|\s*\d{3}", ln)]
        rows = rows or [["001", "done-one", "done", "solo", "alongside", "thr_old"]]   # a board is never zero tickets
        for tid, slug, status, _mode, _runs, worker in rows:
            d = self.tickets / f"{tid}-{slug}"
            d.mkdir()
            m = re.match(r"blocked \(was (\w+)\)", status)
            if status == "draft":
                continue
            line = f"blocked was={m.group(1)}" if m else status
            if worker:
                line = line.replace(" was=", f" worker={worker} was=") if m else f"{line} worker={worker}"
            (d / "status").write_text(line + "\n")

    def run_wd(self, threads=None, *extra, router=ROUTER, raw=None, env=None):
        if raw is not None:
            self.threads.write_text(raw)
        elif threads is not None:
            self.threads.write_text(json.dumps(threads))
        e = {k: v for k, v in os.environ.items() if not k.startswith("ROUTER_")}
        e.update(env or {})
        cmd = [sys.executable, str(WATCHDOG), "--tickets", str(self.tickets), "--now-ms", str(NOW), *extra]
        if router:
            cmd += ["--router", router]
        if threads is not None or raw is not None:
            cmd += ["--input", str(self.threads)]
        p = subprocess.run(cmd, capture_output=True, text=True, env=e)
        return p.returncode, p.stdout, p.stderr


class Flags(Setup):
    def test_each_condition_flags_exactly_once(self):
        rc, out, err = self.run_wd(healthy())
        self.assertEqual((rc, err), (1, ""))
        lines = out.strip().split("\n")
        kinds = {l.split()[0]: l for l in lines}
        self.assertEqual(sorted(kinds), ["FAILED", "FINISHED_UNREVIEWED", "ORPHAN", "STALLED", "WAITING_HUMAN"])
        self.assertEqual(len(lines), 5)
        self.assertIn("thr_bad", kinds["FAILED"])
        self.assertIn("thr_ask", kinds["WAITING_HUMAN"])
        self.assertIn("thr_quiet", kinds["STALLED"])
        self.assertIn("background commands: 1", kinds["STALLED"])
        self.assertIn("thr_fin", kinds["FINISHED_UNREVIEWED"])
        self.assertIn("thr_gone", kinds["ORPHAN"])
        self.assertIn("ticket 006", kinds["ORPHAN"])

    def test_clean_is_silent_exit_zero(self):
        threads = [thread(ROUTER, "active", parent=None), thread("thr_run", "active", age_min=2)]
        self.set_board(BOARD.split("| 003")[0])
        # the board above kept 001 and 002 only (003 onwards cut off)
        rc, out, err = self.run_wd(threads)
        self.assertEqual((rc, out, err), (0, "", ""))

    def test_stall_boundary_and_option(self):
        mk = lambda age: [thread(ROUTER, "active", parent=None), thread("thr_run", "active", age_min=age)]
        board = "| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n| 002 | r | doing | solo | alongside | thr_run |\n"
        self.set_board(board)
        self.assertEqual(self.run_wd(mk(19))[0], 0)
        self.assertEqual(self.run_wd(mk(21))[0], 1)
        self.assertEqual(self.run_wd(mk(21), "--stall-min", "30")[0], 0)
        self.assertEqual(self.run_wd(mk(21), env={"ROUTER_STALL_MIN": "30"})[0], 0)

    def test_idle_child_with_ticket_review_is_not_flagged(self):
        board = "| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n| 002 | r | review | solo | alongside | thr_run |\n"
        self.set_board(board)
        rc, out, _ = self.run_wd([thread(ROUTER, "active", parent=None), thread("thr_run", "idle")])
        self.assertEqual((rc, out), (0, ""))

    def test_waiting_beats_stalled(self):
        board = "| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n| 002 | r | doing | solo | alongside | thr_run |\n"
        self.set_board(board)
        rc, out, _ = self.run_wd([thread(ROUTER, "active", parent=None), thread("thr_run", "active", age_min=90, pending=True)])
        self.assertEqual(out.strip().count("\n"), 0)
        self.assertTrue(out.startswith("WAITING_HUMAN"))

    def test_children_of_other_parents_are_ignored(self):
        board = "| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n"
        self.set_board(board)
        rc, out, _ = self.run_wd([thread(ROUTER, "active", parent=None), thread("thr_x", "active", age_min=999, parent="thr_other")])
        self.assertEqual((rc, out), (0, ""))

    def test_json_output(self):
        rc, out, _ = self.run_wd(healthy(), "--json")
        self.assertEqual(rc, 1)
        kinds = sorted(f["kind"] for f in json.loads(out)["flags"])
        self.assertEqual(kinds, ["FAILED", "FINISHED_UNREVIEWED", "ORPHAN", "STALLED", "WAITING_HUMAN"])

    def test_router_and_board_from_environment(self):
        e = {"ROUTER_THREAD_ID": ROUTER, "ROUTER_TICKETS": str(self.tickets)}
        self.threads.write_text(json.dumps(healthy()))
        p = subprocess.run([sys.executable, str(WATCHDOG), "--input", str(self.threads), "--now-ms", str(NOW)],
                           capture_output=True, text=True, env={**os.environ, **e})
        self.assertEqual(p.returncode, 1)
        self.assertIn("STALLED", p.stdout)


class Unknown(Setup):
    """The positive controls: an unreadable world must not read as a quiet one."""

    def assert_unknown(self, result, needle=""):
        rc, out, err = result
        self.assertEqual(rc, 2, (out, err))
        self.assertEqual(out, "")
        self.assertIn("UNKNOWN", err)
        self.assertIn(needle, err)

    def test_empty_output(self):
        self.assert_unknown(self.run_wd(raw=""), "no output")

    def test_not_json(self):
        self.assert_unknown(self.run_wd(raw="room-cli: server not running"), "not JSON")

    def test_empty_list(self):
        self.assert_unknown(self.run_wd(raw="[]"), "non-empty list")

    def test_json_object_not_list(self):
        self.assert_unknown(self.run_wd(raw='{"error": "unauthorized"}'), "non-empty list")

    def test_router_missing_from_list_is_a_partial_read(self):
        self.assert_unknown(self.run_wd([thread("thr_other", "idle", parent=None)]), "router thread thr_router")

    def test_malformed_entry(self):
        self.assert_unknown(self.run_wd([thread(ROUTER, parent=None), {"title": "no id"}]), "entry 1")

    def test_active_child_without_updatedat(self):
        t = thread("thr_run", "active")
        del t["updatedAt"]
        self.assert_unknown(self.run_wd([thread(ROUTER, parent=None), t]), "updatedAt")

    def test_board_unreadable(self):
        shutil.rmtree(self.tickets)
        self.assert_unknown(self.run_wd(healthy()), "cannot read tickets folder")

    def test_an_unreadable_status_file_is_unknown_not_not_doing(self):
        if os.geteuid() == 0:
            self.skipTest("root reads any file")
        path = sorted(self.tickets.glob("*/status"))[0]
        path.chmod(0)
        try:
            self.assert_unknown(self.run_wd(healthy()), "cannot read")
        finally:
            path.chmod(0o644)

    def test_an_empty_status_file_is_unknown_not_not_doing(self):
        sorted(self.tickets.glob("*/status"))[0].write_text("")
        self.assert_unknown(self.run_wd(healthy()), "is empty")

    def test_tickets_folder_without_tickets(self):
        shutil.rmtree(self.tickets)
        self.tickets.mkdir()                      # exists, but holds no tickets: a wrong path, not "nothing to do"
        self.assert_unknown(self.run_wd(healthy()), "no ticket folders")

    def test_no_router_id(self):
        self.assert_unknown(self.run_wd(healthy(), router=None), "no router thread id")

    def test_input_file_missing(self):
        p = subprocess.run([sys.executable, str(WATCHDOG), "--router", ROUTER, "--tickets", str(self.tickets),
                            "--input", str(self.dir / "nope.json")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("UNKNOWN", p.stderr)
        self.assertIn("cannot read --input", p.stderr)

    def fake_cli(self, body: str) -> dict:
        cli = self.dir / "fake-room-cli"
        cli.write_text("#!/bin/sh\n" + body + "\n")
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
        return {"ROOM_CLI": str(cli)}

    def run_live(self, env):
        p = subprocess.run([sys.executable, str(WATCHDOG), "--router", ROUTER, "--tickets", str(self.tickets), "--now-ms", str(NOW)],
                           capture_output=True, text=True, env={**os.environ, **env})
        return p.returncode, p.stdout, p.stderr

    def test_room_cli_exits_nonzero(self):
        self.assert_unknown(self.run_live(self.fake_cli("echo boom >&2; exit 3")), "exited 3")

    def test_room_cli_prints_nothing(self):
        self.assert_unknown(self.run_live(self.fake_cli("exit 0")), "no output")

    def test_room_cli_missing_binary(self):
        self.assert_unknown(self.run_live({"ROOM_CLI": str(self.dir / "does-not-exist")}), "failed to run")

    def test_room_cli_happy_path_reaches_the_same_verdict(self):
        self.threads.write_text(json.dumps(healthy()))
        rc, out, err = self.run_live(self.fake_cli(f"cat {shlex.quote(str(self.threads))}"))
        self.assertEqual(rc, 1, err)
        self.assertIn("ORPHAN", out)


FAKE_CLI = """import json, os, sys
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
fail = os.environ.get("FAKE_FAIL", "")
args = sys.argv[1:]
if args[:3] == ["thread", "queue", "create"]:
    if fail == "create":
        print("queue is full", file=sys.stderr)
        sys.exit(4)
    if fail == "noid":
        print(json.dumps({{"ok": True}}))
        sys.exit(0)
    print(json.dumps({{"id": "qmsg_1", "threadId": args[3]}}))
elif args[:3] == ["thread", "queue", "send"]:
    if fail == "send":
        sys.exit(5)
    print(json.dumps({{"ok": True}}))
else:
    sys.exit(9)
"""


class Notify(Setup):
    """With --notify the watchdog tells the router itself: a script loop has no agent to do it."""

    def setUp(self):
        super().setUp()
        self.log = self.dir / "calls.jsonl"
        self.state = self.dir / "state.json"
        self.cli = self.dir / "fake-room-cli"
        script = self.dir / "fake-room-cli.py"
        script.write_text(FAKE_CLI.format())
        # A kernel shebang splits interpreter paths at spaces; keep the same Python.
        self.cli.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n')
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IXUSR)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def notify(self, threads, now_offset_min=0, fail="", extra=()):
        env = {"ROOM_CLI": str(self.cli), "FAKE_LOG": str(self.log), "FAKE_FAIL": fail}
        self.threads.write_text(json.dumps(threads))
        cmd = [sys.executable, str(WATCHDOG), "--router", ROUTER, "--tickets", str(self.tickets), "--input", str(self.threads),
               "--now-ms", str(NOW + int(now_offset_min * MIN)), "--notify", "--state", str(self.state), *extra]
        p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **env})
        return p.returncode, p.stdout, p.stderr

    def test_flags_are_queued_to_the_router_with_create_only(self):
        rc, out, err = self.notify(healthy())
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("STALLED thr_quiet", out)
        calls = self.calls()
        self.assertEqual(len(calls), 1, "create alone: on an idle router it is delivered at once, send would 404")
        self.assertEqual(calls[0][:4], ["thread", "queue", "create", ROUTER])
        self.assertIn("--json", calls[0])
        for kind in ("STALLED thr_quiet", "ORPHAN thr_gone", "FAILED thr_bad", "WAITING_HUMAN thr_ask", "FINISHED_UNREVIEWED thr_fin"):
            self.assertIn(kind, calls[0][4])
        self.assertFalse([c for c in calls if c[:3] == ["thread", "queue", "send"]])

    def test_clean_run_sends_nothing(self):
        self.set_board("| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n")
        rc, out, _ = self.notify([thread(ROUTER, "active", parent=None)])
        self.assertEqual((rc, out, self.calls()), (0, "", []))

    def test_same_flags_are_not_resent_until_the_renotify_window_passes(self):
        # One stuck worker whose flag cannot change with the clock (others would turn STALLED as time passes).
        self.set_board("| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n"
                              "| 003 | quiet | doing | solo | alongside | thr_quiet |\n")
        stuck = [thread(ROUTER, "active", parent=None), thread("thr_quiet", "active", age_min=45)]
        self.notify(stuck)
        self.assertEqual(len(self.calls()), 1)
        self.notify(stuck, now_offset_min=10)     # same flag, detail text now says 55 min
        self.assertEqual(len(self.calls()), 1, "repeat flags must not spam the router")
        self.notify(stuck, now_offset_min=59)
        self.assertEqual(len(self.calls()), 1, "still inside the 60 minute window")
        self.notify(stuck, now_offset_min=61)     # still stuck an hour later: remind once
        self.assertEqual(len(self.calls()), 2)
        self.assertIn("STALLED thr_quiet", self.calls()[1][4])

    def test_a_changed_flag_set_is_sent_at_once(self):
        self.notify(healthy())
        more = healthy() + [thread("thr_new", "error")]
        self.set_board(BOARD + "| 010 | new | doing | solo | alongside | thr_new |\n")
        self.notify(more, now_offset_min=1)
        self.assertEqual(len(self.calls()), 2)
        self.assertIn("FAILED thr_new", self.calls()[1][4])

    def test_recovery_forgets_the_state_so_a_new_problem_is_reported(self):
        self.notify(healthy())
        self.set_board("| id | slug | status | mode | runs | worker |\n|--|--|--|--|--|--|\n")
        self.notify([thread(ROUTER, "active", parent=None)], now_offset_min=5)
        self.assertFalse(self.state.exists())
        self.set_board(BOARD)
        self.notify(healthy(), now_offset_min=6)
        self.assertEqual(len(self.calls()), 2)

    def test_queue_create_failure_is_unknown_and_is_retried_next_tick(self):
        rc, out, err = self.notify(healthy(), fail="create")
        self.assertEqual(rc, 2)
        self.assertIn("UNKNOWN", err)
        self.assertIn("queue is full", err)
        self.assertFalse(self.state.exists(), "a failed notification must not count as delivered")
        rc, _, _ = self.notify(healthy(), now_offset_min=1)
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls()[-1][:3], ["thread", "queue", "create"])
        self.assertTrue(self.state.exists())

    def test_a_create_reply_without_an_id_is_unknown(self):
        rc, _, err = self.notify(healthy(), fail="noid")
        self.assertEqual(rc, 2)
        self.assertIn("no message id", err)
        self.assertFalse(self.state.exists())

    def test_notify_from_the_environment_for_a_script_loop(self):
        self.threads.write_text(json.dumps(healthy()))
        env = {**os.environ, "ROOM_CLI": str(self.cli), "FAKE_LOG": str(self.log), "ROUTER_NOTIFY": "1",
               "ROUTER_STATE": str(self.state), "ROUTER_THREAD_ID": ROUTER, "ROUTER_TICKETS": str(self.tickets)}
        p = subprocess.run([sys.executable, str(WATCHDOG), "--input", str(self.threads), "--now-ms", str(NOW)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.calls()), 1)

    def test_without_notify_nothing_is_sent(self):
        self.threads.write_text(json.dumps(healthy()))
        env = {**os.environ, "ROOM_CLI": str(self.cli), "FAKE_LOG": str(self.log)}
        p = subprocess.run([sys.executable, str(WATCHDOG), "--router", ROUTER, "--tickets", str(self.tickets),
                            "--input", str(self.threads), "--now-ms", str(NOW)], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.calls(), [])


class ParserAgreement(Setup):
    """watchdog.py carries its own status-file reader (a loop stores a lone copy of the file).
    It must agree with board.py about which tickets are doing, and with whom."""

    def test_same_doing_set(self):
        sys.path.insert(0, str(WATCHDOG.parent))
        try:
            import board as b
            import watchdog as w
        finally:
            sys.path.pop(0)
        for d in self.tickets.iterdir():                  # board.py also wants prd/eval/APPROVED to load as valid
            (d / "prd.md").write_text("---\nmode: solo\nruns: alongside\n---\nx\n")
            (d / "eval.md").write_text("x\n")
            (d / "APPROVED").write_text("")
        theirs = {t["id"]: t["worker"] for t in b.load(self.tickets).tickets if t["status"] == "doing"}
        ours = w.read_board_doing(str(self.tickets))
        self.assertEqual(ours, theirs)
        self.assertEqual(len(ours), 6)
        self.assertNotIn("009", ours, "a blocked ticket is not being worked")

    def test_a_generated_board_md_is_never_read(self):
        sys.path.insert(0, str(WATCHDOG.parent))
        try:
            import watchdog as w
        finally:
            sys.path.pop(0)
        (self.tickets / "board.md").write_text("| 008 | queued | doing | solo | alongside | thr_fake |\n")
        self.assertNotIn("008", w.read_board_doing(str(self.tickets)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
