"""Tests for install_orchestrator.py (spec AC-3). launchctl is a stub script that records its calls."""
import importlib.util
import os
import plistlib
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.join(HERE, "..", "install", "install_orchestrator.py")


def load():
    spec = importlib.util.spec_from_file_location("install_orchestrator_under_test", INSTALLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


I = load()
LABELS = ("com.unite.orchestrator", "com.unite.orchestrator-deadman")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.agents = os.path.join(t, "LaunchAgents")
        self.state = os.path.join(t, "state")
        self.calls = os.path.join(t, "calls.log")
        self.loaded = os.path.join(t, "loaded")
        os.makedirs(self.loaded)
        self.stub = os.path.join(t, "launchctl")
        with open(self.stub, "w") as f:
            f.write("#!/bin/sh\n"
                    'echo "$@" >> "%s"\n'
                    'L="%s"\n'
                    'case "$1" in\n'
                    '  print) [ -f "$L/$(basename "$2")" ] ;;\n'
                    '  bootstrap) touch "$L/$(basename "$3" .plist)" ;;\n'
                    '  bootout) rm -f "$L/$(basename "$2")" ;;\n'
                    'esac\n' % (self.calls, self.loaded))
        os.chmod(self.stub, 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_inst(self, *extra, host="Phills-Mac-mini.local"):
        with mock.patch.object(I.socket, "gethostname", return_value=host):
            return I.main(list(extra), agents=self.agents, state=self.state, launchctl=self.stub)

    def plists(self):
        out = {}
        for label in LABELS:
            with open(os.path.join(self.agents, label + ".plist"), "rb") as f:
                out[label] = f.read()
        return out

    def test_install_twice_is_identical_and_loaded(self):
        self.assertEqual(self.run_inst(), 0)
        first = self.plists()
        self.assertEqual(self.run_inst(), 0)
        self.assertEqual(self.plists(), first)
        self.assertEqual(sorted(os.listdir(self.loaded)), sorted(LABELS))
        p = plistlib.loads(first["com.unite.orchestrator-deadman"])
        self.assertEqual(p["ProgramArguments"][-1], "--deadman")
        self.assertEqual(p["StartInterval"], 900)
        self.assertEqual(plistlib.loads(first["com.unite.orchestrator"])["StartInterval"], 1800)

    def test_launchd_never_opens_a_log_path(self):
        self.assertEqual(self.run_inst(), 0)
        for label, raw in self.plists().items():
            p = plistlib.loads(raw)
            for key in ("StandardOutPath", "StandardErrorPath"):
                self.assertEqual(p.get(key), "/dev/null", "%s %s" % (label, key))

    def test_uninstall_removes_plists_and_writes_marker(self):
        self.run_inst()
        self.assertEqual(self.run_inst("--uninstall"), 0)
        for label in LABELS:
            self.assertFalse(os.path.exists(os.path.join(self.agents, label + ".plist")))
        self.assertEqual(os.listdir(self.loaded), [])
        self.assertTrue(os.path.exists(os.path.join(self.state, "ORCHESTRATOR-DISABLED")))

    def test_reinstall_refused_while_marker_exists(self):
        self.run_inst()
        self.run_inst("--uninstall")
        self.assertEqual(self.run_inst(), 3)
        self.assertFalse(os.path.exists(os.path.join(self.agents, LABELS[0] + ".plist")))
        self.assertEqual(os.listdir(self.loaded), [])

    def test_host_flag_cannot_claim_the_mini(self):
        with mock.patch.object(I.socket, "gethostname", return_value="Phills-MacBook-Pro.local"):
            rc = I.main(["--host", "Phills-Mac-mini.local"], agents=self.agents, state=self.state,
                        launchctl=self.stub)
        self.assertNotEqual(rc, 0)
        self.assertFalse(os.path.exists(self.agents))
        self.assertFalse(os.path.exists(self.calls))

    def test_path_flags_cannot_dodge_the_disabled_marker(self):
        home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(home, ".local", "state", "orchestrator"))
        open(os.path.join(home, ".local", "state", "orchestrator", "ORCHESTRATOR-DISABLED"), "w").close()
        alt = os.path.join(self.tmp.name, "alternate-state")
        for flags in (["--state-dir", alt], ["--agents-dir", self.agents], ["--launchctl", self.stub]):
            with mock.patch.object(I, "HOME", home), \
                    mock.patch.object(I.socket, "gethostname", return_value="Phills-Mac-mini.local"):
                rc = I.main(["--agents-dir", self.agents, "--state-dir", alt, "--launchctl", self.stub])
                rc_one = I.main(flags)
            self.assertEqual(rc, 2)
            self.assertEqual(rc_one, 2)
            self.assertFalse(os.path.exists(self.agents))
            self.assertFalse(os.path.exists(self.calls))

    def test_other_hosts_do_nothing(self):
        self.assertEqual(self.run_inst(host="Phills-MacBook-Pro.local"), 0)
        self.assertFalse(os.path.exists(self.agents))
        self.assertFalse(os.path.exists(self.calls))


if __name__ == "__main__":
    unittest.main()
