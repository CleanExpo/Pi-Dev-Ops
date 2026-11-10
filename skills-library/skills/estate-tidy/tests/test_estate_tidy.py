#!/usr/bin/env python3
"""Regression tests for estate-tidy's destructive steps and its installer.

Each test plants the input an independent review (Codex, 01/11/2026, head 640da9de) used to
show data loss, then asserts the data survives:
  - temp sweep through a symlinked scratch root deleted the link target's files;
  - a listening service run from /tmp was classified throwaway and SIGKILLed mid-write;
  - a sessions-mode file with a newline injected a second ExecStart into a root unit;
  - an installer destination that was a symlink overwrote the file it pointed at.
Also runs the script's own --selftest so CI exercises it on every change.
"""
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


et = load("estate_tidy_under_test", HERE / "estate_tidy.py")
inst = load("install_estate_tidy_under_test", HERE / "install" / "install_estate_tidy.py")
HOUR = 3600


def aged(path, hours):
    t = time.time() - hours * HOUR
    os.utime(path, (t, t))


class CanonicalScript(unittest.TestCase):
    def test_optional_paths_preserve_precedence_and_propagate_other_errors(self):
        from unittest.mock import Mock, patch
        denied = Mock(); denied.exists.side_effect = PermissionError("other account")
        missing = Mock(); missing.exists.return_value = False
        available = Mock(); available.exists.return_value = True
        with patch.object(inst, "_CANON", [denied, missing, available]):
            self.assertIs(inst.canonical_script(), available)
        with patch.object(inst, "_CANON", [denied, missing]):
            self.assertEqual(inst.canonical_script(), inst.HERE / "estate_tidy.py")
        broken = Mock(); broken.exists.side_effect = OSError("I/O error")
        with patch.object(inst, "_CANON", [broken]):
            with self.assertRaises(OSError):
                inst.canonical_script()


class TempSweep(unittest.TestCase):
    def run_gc(self, roots):
        saved = et.tmp_roots
        et.tmp_roots = lambda R: roots
        try:
            R = types.SimpleNamespace(machine="macbook", dry=False, agent=None, report={"disk_actions": []})
            et.tmp_gc(R)
            return R.report["disk_actions"][-1]
        finally:
            et.tmp_roots = saved

    def test_symlinked_root_is_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d, "owner-data")
            target.mkdir()
            keep = target / "owner-data.txt"
            keep.write_text("not scratch")
            aged(keep, 72)
            link = Path(d, "claude-review-link")
            link.symlink_to(target, target_is_directory=True)
            self.run_gc([(link, 24 * HOUR)])
            self.assertTrue(keep.exists(), "file behind a symlinked temp root was deleted")

    def test_real_root_still_swept(self):
        # positive control: the sweep still deletes old scratch under a real root
        with tempfile.TemporaryDirectory() as d:
            root = Path(d, "claude-real")
            root.mkdir()
            old = root / "scratch.txt"
            old.write_text("x")
            aged(old, 72)
            fresh = root / "fresh.txt"
            fresh.write_text("y")
            act = self.run_gc([(root, 24 * HOUR)])
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertEqual(act["deleted"], 1)


class ProcessClassifier(unittest.TestCase):
    base = {"ppid": 1, "age_s": 4 * HOUR, "user": "u"}

    def test_listening_temp_script_is_left_alone(self):
        kill, why = et.kill_candidate(dict(self.base, cmd="python3 /private/tmp/svc/server.py"), {8123}, set(), 9)
        self.assertFalse(kill, why)

    def test_listening_bridge_child_temp_script_is_left_alone(self):
        info = dict(self.base, ppid=55, age_s=13 * HOUR, bridge_child="desktop-commander",
                    cmd="node /tmp/lanes/server.cjs")
        kill, why = et.kill_candidate(info, {4000}, set(), 9)
        self.assertFalse(kill, why)

    def test_stdlib_preview_server_still_stopped(self):
        info = dict(self.base, cmd="python3 -m http.server 8878 --directory /tmp/l")
        self.assertTrue(et.kill_candidate(info, {8878}, set(), 9)[0])

    def test_quiet_temp_script_still_stopped(self):
        self.assertTrue(et.kill_candidate(dict(self.base, cmd="python3 /tmp/lanes/run.py"), set(), set(), 9)[0])

    def test_names_containing_a_dev_marker_are_not_dev_servers(self):
        # every kill rule matched raw substrings: "invite" holds "vite", "revitest" holds "vitest", ...
        services = ["/usr/local/bin/node /opt/prod/invite-api/index.js",
                    "node /srv/webpackage-store/server.js",
                    "node /srv/nodemonitor/app.js",
                    "node /srv/storybookings/index.js",
                    "node /srv/next-serverless-shim/index.js",
                    "node /srv/revitest-reports/index.js",
                    "node /srv/app/index.js --devtools",
                    "/opt/chromatic-sync/bin/sync --headless",
                    "node /srv/ms-playwright-docs/helper.js"]
        for cmd in services:
            kill, why = et.kill_candidate(dict(self.base, cmd=cmd), {3000}, set(), 9)
            self.assertFalse(kill, "%s -> %s" % (cmd, why))

    def test_real_dev_servers_still_stopped(self):
        devs = ["node /x/node_modules/.bin/vite --port 5173",
                "node /x/node_modules/vite/bin/vite.js",
                "node /x/node_modules/.bin/webpack serve",
                "node /x/node_modules/.bin/nodemon src/index.ts",
                "node /x/node_modules/.bin/storybook dev -p 6006",
                "node /x/node_modules/.bin/next dev -p 3001",
                "next-server (v16.4.2)",
                "node /x/node_modules/.bin/astro dev",
                "node /x/server.js dev"]
        for cmd in devs:
            kill, why = et.kill_candidate(dict(self.base, cmd=cmd), {5173}, set(), 9)
            self.assertTrue(kill, "%s -> %s" % (cmd, why))


class StopProcess(unittest.TestCase):
    @staticmethod
    def reaper(p):
        def wait(pid, secs):
            try:
                p.wait(timeout=secs)
                return True
            except subprocess.TimeoutExpired:
                return False
        return wait

    def test_python_script_runs_its_finally_block(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d, "state.txt")
            script = Path(d, "job.py")
            script.write_text("import time\ntry:\n    while True: time.sleep(0.1)\n"
                              "finally:\n    open(%r, 'w').write('saved')\n" % str(state))
            p = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(0.5)
                sig = et.stop_process(p.pid, wait=self.reaper(p))
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
            self.assertEqual(state.read_text() if state.exists() else "", "saved",
                             "pending state lost; stopped with %s" % sig)


class InstallerMode(unittest.TestCase):
    def test_valid_modes(self):
        for m in ("off", "dry", "on"):
            self.assertEqual(inst.parse_mode(m + "\n"), m)

    def test_injected_directive_refused(self):
        for bad in ("off\nExecStart=/bin/true\n", "on ExecStart=/x", "", "ON", "dry\n\n--x"):
            self.assertIsNone(inst.parse_mode(bad), repr(bad))


class InstallerWrite(unittest.TestCase):
    # literal, so the suite still loads (and fails test by test) against an installer without SVC_OWNER
    OWN = "Description=estate-tidy 2-hourly settle, handoff and cleanup pass"
    UNIT = "[Unit]\n%s\n[Service]\nExecStart=/bin/true\n" % OWN

    def test_symlink_destination_refused(self):
        with tempfile.TemporaryDirectory() as d:
            other = Path(d, "unrelated.txt")
            other.write_text("original")
            link = Path(d, "estate-tidy.service")
            link.symlink_to(other)
            with self.assertRaises(inst.RefusedWrite):
                inst.write_if_changed(link, self.UNIT, False, [], self.OWN)
            self.assertEqual(other.read_text(), "original")
            self.assertTrue(link.is_symlink())

    def test_symlink_to_an_owned_looking_file_refused(self):
        # the symlink rule must hold on its own, not only because the target lacks the owner line
        with tempfile.TemporaryDirectory() as d:
            other = Path(d, "elsewhere.service")
            other.write_text(self.UNIT.replace("/bin/true", "/bin/false"))
            link = Path(d, "estate-tidy.service")
            link.symlink_to(other)
            with self.assertRaises(inst.RefusedWrite):
                inst.write_if_changed(link, self.UNIT, False, [], self.OWN)
            self.assertIn("/bin/false", other.read_text())

    def test_foreign_file_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "com.unite.estate-tidy.plist")
            p.write_text("someone else's job")
            with self.assertRaises(inst.RefusedWrite):
                inst.write_if_changed(p, self.UNIT, False, [], self.OWN)
            self.assertEqual(p.read_text(), "someone else's job")

    def test_file_that_only_mentions_the_name_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "com.other.plist")
            p.write_text("# mentions estate-tidy and estate_tidy in a comment\n<plist>other</plist>\n")
            for owner, text in ((self.OWN, self.UNIT),
                                (inst.plist_owner(inst.LABEL), inst.plist(inst.LABEL, ["/x"], minute=0, logdir="/l"))):
                with self.assertRaises(inst.RefusedWrite):
                    inst.write_if_changed(p, text, False, [], owner)
            self.assertIn("<plist>other</plist>", p.read_text())

    def test_owner_line_is_what_every_writer_emits(self):
        # each call site's owner line must be in what it writes, or every update would refuse its own file
        self.assertIn(inst.plist_owner(inst.LABEL), inst.plist(inst.LABEL, ["/x"], minute=0, logdir="/l").splitlines())
        self.assertIn(inst.SCRIPT_OWNER, (HERE / "estate_tidy.py").read_text().splitlines())

    def test_owned_file_replaced_and_new_file_written(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "estate-tidy.service")
            changed = []
            v2 = self.UNIT.replace("/bin/true", "/bin/v2")
            self.assertTrue(inst.write_if_changed(p, self.UNIT, False, changed, self.OWN))
            self.assertTrue(inst.write_if_changed(p, v2, False, changed, self.OWN))
            self.assertEqual(p.read_text(), v2)
            self.assertFalse(inst.write_if_changed(p, v2, False, changed, self.OWN))


class InFileSelftest(unittest.TestCase):
    def test_selftest_passes(self):
        r = subprocess.run([sys.executable, str(HERE / "estate_tidy.py"), "--selftest"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
