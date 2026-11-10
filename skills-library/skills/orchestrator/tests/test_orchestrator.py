"""Tests for orchestrator.py. Stdlib unittest; every path points into a temp dir.

ORCH_UNDER_TEST, when set, names the orchestrator.py to load (run_mutants.py points it at a
mutated copy); otherwise the real script beside this folder is tested.
"""
import fcntl
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("ORCH_UNDER_TEST") or os.path.join(HERE, "..", "scripts", "orchestrator.py")


def load():
    spec = importlib.util.spec_from_file_location("orchestrator_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


O = load()
LOGGED_IN = {"state": "LOGGED_IN", "reason": "logged_in"}


def job(i, **kw):
    j = {"id": i, "title": "job %s" % i, "status": "todo", "project": "ccw", "created": "2026-10-0%s" % (len(i) % 9)}
    j.update(kw)
    return j


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.vol = os.path.join(t, "vol")
        os.makedirs(os.path.join(self.vol, "ops"))
        os.makedirs(os.path.join(self.vol, "session-handoffs"))
        self.cfg = {
            "board": os.path.join(self.vol, "ops", "jobs.json"),
            "volume": self.vol,
            "state": os.path.join(t, "state"),
            "mirror": os.path.join(self.vol, "ops", "MORNING.md"),
            "hard_stop": os.path.join(t, "HARD_STOP"),
            "needs_phill": os.path.join(self.vol, "session-handoffs", "NEEDS-PHILL.md"),
            "is_mounted": lambda p: True,
        }
        self.write_board([job("A1"), job("A2", priority="P1")])
        self.lanes = mock.patch.object(O, "probe_lanes", return_value={"claude": dict(LOGGED_IN)})
        self.lanes.start()
        self.tmux = mock.patch.object(O, "idle_sessions", return_value=[])
        self.tmux.start()

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def write_board(self, jobs, **extra):
        d = {"jobs": jobs}
        d.update(extra)
        with open(self.cfg["board"], "w") as f:
            json.dump(d, f)

    @staticmethod
    def raw(path):
        with open(path, "rb") as f:
            return f.read()

    def rows(self):
        return O.read_rows(self.cfg)

    def page(self):
        with open(os.path.join(self.cfg["state"], "MORNING.md")) as f:
            return f.read()

    def all_output(self):
        text = ""
        for root, _, files in os.walk(self.tmp.name):
            for n in files:
                if n != "jobs.json":
                    with open(os.path.join(root, n), errors="replace") as f:
                        text += f.read()
        return text


class TestRun(Base):
    def test_normal_run_writes_page_row_and_mirror(self):
        row = O.run(self.cfg)
        self.assertTrue(row["ok"])
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(self.page().startswith("Generated "))
        self.assertTrue(os.path.exists(self.cfg["mirror"]))
        self.assertIn("A2", self.page())

    def test_missing_priority_is_ranked_last(self):
        self.write_board([job("NOPRIO"), job("HASPRIO", priority="P2")])
        row = O.run(self.cfg)
        self.assertTrue(row["ok"], row["error"])
        page = self.page()
        self.assertLess(page.index("HASPRIO"), page.index("NOPRIO"))

    def test_malformed_board_is_reported_not_empty(self):
        with open(self.cfg["board"], "w") as f:
            f.write("{not json")
        before = self.raw(self.cfg["board"])
        row = O.run(self.cfg)
        self.assertFalse(row["ok"])
        self.assertFalse(row["board_read"])
        self.assertIsNone(row["jobs"])
        self.assertIn("BOARD UNREADABLE", self.page())
        self.assertNotIn("No todo jobs", self.page())
        self.assertEqual(self.raw(self.cfg["board"]), before)

    def test_unreadable_board_is_reported(self):
        os.remove(self.cfg["board"])
        row = O.run(self.cfg)
        self.assertFalse(row["ok"])
        self.assertIn("board_unreadable", row["error"])
        self.assertIn("BOARD UNREADABLE", self.page())

    def test_unmounted_volume_never_reads_board_or_creates_dirs(self):
        self.cfg["is_mounted"] = lambda p: False
        spy = mock.patch.object(O, "load_board", wraps=O.load_board).start()
        row = O.run(self.cfg)
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(row["error"], "volume_not_mounted")
        self.assertTrue(self.page().split("\n")[2:] and "BOARD UNREADABLE" in self.page())
        self.assertFalse(os.path.exists(self.cfg["mirror"]))

    def test_hard_stop_never_opens_board(self):
        open(self.cfg["hard_stop"], "w").close()
        spy = mock.patch.object(O, "load_board", wraps=O.load_board).start()
        row = O.run(self.cfg)
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(row["skipped"], "hard_stop")
        self.assertEqual(len(self.rows()), 1)
        self.assertIn("PAUSED by HARD_STOP", self.page())

    def test_outputs_never_overwrite_the_inputs(self):
        with open(self.cfg["needs_phill"], "w") as f:
            f.write("- item\n")
        state = self.cfg["state"]
        os.makedirs(state)
        alias = os.path.join(self.tmp.name, "board-alias.json")
        os.symlink(self.cfg["board"], alias)
        hard = os.path.join(self.tmp.name, "board-hard.json")
        os.link(self.cfg["board"], hard)
        cases = [("mirror", self.cfg["board"]), ("mirror", self.cfg["needs_phill"]), ("mirror", alias),
                 ("mirror", hard),
                 ("board", os.path.join(state, "MORNING.md")),
                 ("needs_phill", os.path.join(state, "orchestrator-runs.jsonl"))]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                cfg = dict(self.cfg, **{key: value})
                before = {p: self.raw(p) for p in (cfg["board"], cfg["needs_phill"]) if os.path.exists(p)}
                logs = sorted(os.listdir(state))
                row = O.run(cfg)
                self.assertFalse(row["ok"])
                self.assertEqual(row["error"], "unsafe_paths")
                self.assertEqual(O.deadman(cfg), "UNSAFE")
                for p, b in before.items():
                    self.assertEqual(self.raw(p), b)
                self.assertEqual(sorted(os.listdir(state)), logs)

    def test_disabled_marker_writes_row_and_banner(self):
        os.makedirs(self.cfg["state"])
        open(os.path.join(self.cfg["state"], "ORCHESTRATOR-DISABLED"), "w").close()
        row = O.run(self.cfg)
        self.assertEqual(row["skipped"], "disabled")
        self.assertIn("ORCHESTRATOR DISABLED", self.page())

    def test_run_lock_blocks_second_instance(self):
        os.makedirs(self.cfg["state"])
        spy = mock.patch.object(O, "load_board", wraps=O.load_board).start()
        with open(os.path.join(self.cfg["state"], "run.lock"), "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            row = subprocess_free_run(self.cfg)
        self.assertEqual(row["skipped"], "locked")
        self.assertEqual(spy.call_count, 0)

    def test_crash_mid_run_still_writes_row(self):
        mock.patch.object(O, "rank", side_effect=RuntimeError("boom")).start()
        row = O.run(self.cfg)
        self.assertFalse(row["ok"])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("RuntimeError", rows[0]["error"])

    def test_two_runs_give_identical_pages_apart_from_time(self):
        O.run(self.cfg)
        a = self.page().split("\n", 1)[1]
        O.run(self.cfg)
        b = self.page().split("\n", 1)[1]
        self.assertEqual(a, b)

    def test_board_bytes_unchanged_by_run(self):
        before = self.raw(self.cfg["board"])
        O.run(self.cfg)
        self.assertEqual(self.raw(self.cfg["board"]), before)

    def test_needs_phill_file_untouched_and_rendered(self):
        with open(self.cfg["needs_phill"], "w") as f:
            f.write("# Needs Phill\n- reconnect LinkedIn\n")
        before = self.raw(self.cfg["needs_phill"])
        O.run(self.cfg)
        self.assertEqual(self.raw(self.cfg["needs_phill"]), before)
        self.assertIn("reconnect LinkedIn", self.page())

    def test_titles_are_escaped(self):
        self.write_board([job("X1", title="`; rm -rf ~` <script>alert(1)</script> [x](http://evil)")])
        O.run(self.cfg)
        page = self.page()
        self.assertNotIn("<script>", page)
        self.assertNotIn("[x](http", page)
        self.assertIsNone(re.search(r"(?<!\\)[`\[\]()]", page.split("## Suggested owners")[1].split("##")[0]))

    def test_watcher_and_filler_jobs_are_not_suggested(self):
        self.write_board([job("W-SITE-1", priority="P0"), job("F1", priority="P0", filler_key="k"), job("REAL1", priority="P3")])
        O.run(self.cfg)
        sugg = self.page().split("## Suggested owners")[1].split("##")[0]
        self.assertNotIn("W-SITE-1", sugg)
        self.assertNotIn("F1", sugg)
        self.assertIn("REAL1", sugg)

    def test_owned_jobs_are_not_suggested(self):
        self.write_board([job("OWNED", assigned_to="PC"), job("FREE")])
        O.run(self.cfg)
        sugg = self.page().split("## Suggested owners")[1].split("##")[0]
        self.assertNotIn("OWNED", sugg)
        self.assertIn("FREE", sugg)

    def test_stalled_doing_job_is_listed(self):
        old = "2026-01-01T00:00:00+00:00"
        self.write_board([job("D1", status="doing", updated=old), job("D2", status="doing")])
        row = O.run(self.cfg)
        self.assertEqual(row["stalls"], 2)
        self.assertIn("no timestamp", self.page())

    def test_large_board_is_fast(self):
        self.write_board([job("J%d" % i, priority="P%d" % (i % 4)) for i in range(2000)])
        t = time.time()
        row = O.run(self.cfg)
        self.assertTrue(row["ok"])
        self.assertLess(time.time() - t, 5)

    def test_empty_board_says_no_todo_jobs(self):
        self.write_board([])
        row = O.run(self.cfg)
        self.assertTrue(row["ok"])
        self.assertIn("No todo jobs", self.page())


def subprocess_free_run(cfg):
    return O.run(cfg)


class TestProbes(Base):
    def setUp(self):
        super().setUp()
        self.lanes.stop()

    def test_lane_down_reason_is_an_enum(self):
        self.assertEqual(O.classify("cursor", 1, "Error: macOS login keychain is locked"), ("NOT_LOGGED_IN", "keychain_locked"))
        self.assertEqual(O.classify("claude", 0, "Logged in as someone"), ("LOGGED_IN", "logged_in"))
        self.assertEqual(O.classify("claude", 1, "Not logged in"), ("NOT_LOGGED_IN", "not_logged_in"))
        self.assertEqual(O.classify("pc", None, ""), ("UNREACHABLE", "timeout"))
        self.assertEqual(O.classify("codex", 0, "something new"), ("UNKNOWN", "unrecognised_output"))

    def test_probe_output_never_reaches_disk(self):
        marker = "FAKE-CRED-MARKER-0000"

        def fake(argv, timeout):
            return 0, "Logged in using an API key - %s" % marker

        mock.patch.object(O, "run_cmd", side_effect=fake).start()
        row = O.run(self.cfg)
        self.assertNotIn(marker, self.all_output())
        self.assertEqual(row["lanes"]["codex"]["reason"], "api_key_mode")

    def test_every_subprocess_argv_is_allow_listed(self):
        seen = []
        real_popen = subprocess.Popen

        def spy(argv, *a, **kw):
            seen.append(tuple(argv))
            return real_popen(["/usr/bin/true"], *a, **kw)

        mock.patch.object(subprocess, "Popen", side_effect=spy).start()
        O.run(self.cfg)
        self.assertTrue(seen)
        for argv in seen:
            self.assertIn(argv, O.ALLOWED_ARGV)

    def test_allow_list_rejects_other_commands(self):
        started = []
        mock.patch.object(subprocess, "Popen", side_effect=lambda *a, **kw: started.append(a)).start()
        with self.assertRaises(ValueError):
            O.run_cmd(("/usr/bin/true", "not-allow-listed"), 1)
        self.assertEqual(started, [])

    def test_probe_timeout_kills_grandchild(self):
        d = tempfile.mkdtemp(dir=self.tmp.name)
        script = os.path.join(d, "slow")
        with open(script, "w") as f:
            f.write(textwrap.dedent("""\
                #!/bin/sh
                sleep 60 &
                sleep 60
                """))
        os.chmod(script, 0o755)
        argv = (script,)
        with mock.patch.object(O, "ALLOWED_ARGV", O.ALLOWED_ARGV | {argv}):
            t = time.time()
            rc, out = O.run_cmd(argv, 1)
        self.assertIsNone(rc)
        self.assertLess(time.time() - t, 10)


class TestDeadman(Base):
    def _row(self, age_s, **kw):
        os.makedirs(self.cfg["state"], exist_ok=True)
        ts = time.time() - age_s
        from datetime import datetime, timezone
        r = {"ts": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "ok": True, "skipped": None}
        r.update(kw)
        with open(os.path.join(self.cfg["state"], "orchestrator-runs.jsonl"), "a") as f:
            f.write(json.dumps(r) + "\n")

    def test_deadman_flags_stale_log(self):
        self._row(2 * 3600)
        self.assertEqual(O.deadman(self.cfg), "STALE")
        self.assertTrue(self.page().startswith("ORCHESTRATOR STALE"))

    def test_deadman_gives_up_on_a_hung_mirror(self):
        # A FIFO blocks open() the way the Mini's hung external drive does (30/10/2026).
        self._row(2 * 3600)
        os.mkfifo(self.cfg["mirror"])
        mock.patch.object(O, "config", return_value=self.cfg).start()
        mock.patch.object(O, "DEADMAN_DEADLINE_S", 1).start()

        def release():
            try:
                os.close(os.open(self.cfg["mirror"], os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass

        timer = threading.Timer(8, release)
        timer.start()
        start = time.time()
        try:
            rc = O.main(["orchestrator.py", "--deadman"])
        finally:
            timer.cancel()
        self.assertLess(time.time() - start, 5)
        self.assertNotEqual(rc, 0)
        self.assertTrue(self.page().startswith("ORCHESTRATOR STALE"))

    def test_run_gives_up_on_a_hung_board(self):
        os.remove(self.cfg["board"])
        os.mkfifo(self.cfg["board"])
        mock.patch.object(O, "config", return_value=self.cfg).start()
        mock.patch.object(O, "RUN_DEADLINE_S", 1).start()

        def release():
            try:
                os.close(os.open(self.cfg["board"], os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass

        timer = threading.Timer(8, release)
        timer.start()
        start = time.time()
        try:
            O.main(["orchestrator.py"])
        finally:
            timer.cancel()
        self.assertLess(time.time() - start, 5)
        with open(os.path.join(self.cfg["state"], "orchestrator-runs.jsonl")) as f:
            self.assertEqual(json.loads(f.read().splitlines()[-1])["error"], "deadline")

    def test_deadman_quiet_on_fresh_log(self):
        self._row(600)
        self.assertEqual(O.deadman(self.cfg), "OK")

    def test_deadman_pause_is_not_stale(self):
        self._row(2 * 3600)
        self._row(60, ok=False, skipped="hard_stop")
        self.assertEqual(O.deadman(self.cfg), "PAUSED")

    def test_deadman_with_no_log_is_stale(self):
        self.assertEqual(O.deadman(self.cfg), "STALE")


class TestPaths(unittest.TestCase):
    def test_defaults_point_at_the_mini_not_a_test_dir(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") or k == "ORCH_UNDER_TEST"}
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = O.config()
        self.assertTrue(cfg["board"].startswith("/Volumes/Mini Mini 2T Storage/"))
        self.assertTrue(cfg["state"].endswith("/.local/state/orchestrator"))


if __name__ == "__main__":
    unittest.main()
