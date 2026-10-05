#!/usr/bin/env python3
"""Controls for the fleet registry and its probe.

Every test here corresponds to a fault that was live in this file on 2026-08-31 and
that produced the SAME visible row as a healthy-but-offline machine. That is the
failure mode fleet-compute exists to prevent and the one it kept committing:
"a broken query and a quiet node look identical".

    python3 test_fleet.py
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fleet  # noqa: E402


class LocalShell(unittest.TestCase):
    """remote() used to run every local probe through a hardcoded `zsh -lc`."""

    def test_local_run_uses_the_nodes_own_shell(self):
        # The regression: a node whose shell is bash (Linux container) or PowerShell
        # (Windows) failed its own local probe with "No such file or directory: 'zsh'"
        # and was reported UNREACHABLE -- identical to a switched-off machine.
        for node in fleet.NODES:
            declared = shlex.split(fleet.NODES[node]["shell"])
            self.assertTrue(declared, f"{node} declares no shell")

    def test_a_node_without_zsh_can_still_probe_itself(self):
        # Runs for real against whatever this machine is. If the hardcode came back,
        # this fails on any host without zsh rather than passing quietly.
        local = fleet.LOCAL_NODE
        if not local or local not in fleet.NODES:
            self.skipTest("not running on a registered node")
        rc, out, err = fleet.remote(local, "echo FLEETPROBE=ok")
        self.assertEqual(rc, 0, f"local probe failed: {err}")
        self.assertIn("FLEETPROBE=ok", out)


class Dialect(unittest.TestCase):
    """POSIX payloads were sent to a PowerShell node for as long as it has existed."""

    def test_windows_is_powershell_and_the_macs_are_not(self):
        self.assertEqual(fleet.dialect("windows"), "powershell")
        for node in ("macbook", "mini"):
            self.assertEqual(fleet.dialect(node), "posix")

    def test_every_dialect_has_a_capacity_and_runtime_payload(self):
        # A node whose dialect has no payload would raise KeyError mid-probe, which
        # reads as a crash rather than as an unsupported node.
        for node in fleet.NODES:
            d = fleet.dialect(node)
            self.assertIn(d, fleet.RUNTIME_PROBES, f"{node}: no runtime probes for {d}")

    def test_powershell_payload_carries_no_posix_isms(self):
        # The actual bug: sysctl/nproc/uptime/2>/dev/null cannot run in PowerShell, so
        # the Windows probe could never have returned a reading, online or not.
        for bad in ("sysctl", "nproc", "uptime", "2>/dev/null", "/proc/meminfo"):
            self.assertNotIn(bad, fleet.CAPACITY_PS, f"PowerShell payload contains {bad!r}")
        for bad in ("&& echo", ">/dev/null"):
            self.assertNotIn(bad, fleet.RUNTIME_PROBES["powershell"]["claude"])

    def test_both_dialects_emit_the_same_three_labelled_keys(self):
        # free_cores must mean the same thing on every node or the fleet total is a
        # sum of different units.
        for payload in (fleet.CAPACITY, fleet.CAPACITY_PS):
            for key in ("FLEETCORES", "FLEETMEM", "FLEETLOAD"):
                self.assertIn(key, payload)


class PowerShellPayloadActuallyParses(unittest.TestCase):
    """The Windows payload's only verification was a substring search.

    `assertNotIn("sysctl", CAPACITY_PS)` is satisfied by the literal string
    "FLEETCORES FLEETMEM FLEETLOAD" — and by anything else that happens not to contain
    the five banned words, including a payload with an unbalanced brace. The Windows
    probe shipped broken twice, and both times the failure rendered as "node
    unreachable", indistinguishable from the machine being switched off.

    PowerShell's own parser settles the syntax question on any platform, so these run on
    a Linux CI runner. What they CANNOT settle is semantics: Get-CimInstance
    Win32_ComputerSystem is Windows-only, so whether the payload returns real numbers is
    still only provable on Windows and is still only structurally claimed here.
    """

    PARSER = (
        "$src = [System.IO.File]::ReadAllText($env:FLEET_PS_FILE);"
        "$errors = $null;"
        "[System.Management.Automation.Language.Parser]::ParseInput("
        "$src, [ref]$null, [ref]$errors) | Out-Null;"
        "if ($errors.Count -gt 0) {"
        "  $errors | ForEach-Object { Write-Output ('PARSE-ERROR: ' + $_.Message) };"
        "  exit 1 };"
        "Write-Output 'PARSE-OK'"
    )

    @staticmethod
    def _pwsh():
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            raise unittest.SkipTest(
                "PowerShell is not installed on this host, so the Windows payload was "
                "NOT parsed and NOT executed. This is not a pass — it is the same "
                "unverified state the payload shipped broken in twice. GitHub's "
                "ubuntu-latest runner has pwsh preinstalled; install it locally to run "
                "these.")
        return exe

    def _parse(self, source: str) -> subprocess.CompletedProcess:
        exe = self._pwsh()
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as fh:
            fh.write(source)
            path = fh.name
        try:
            env = dict(os.environ, FLEET_PS_FILE=path)
            return subprocess.run([exe, "-NoProfile", "-NonInteractive",
                                   "-Command", self.PARSER],
                                  capture_output=True, text=True, timeout=120, env=env)
        finally:
            os.unlink(path)

    def test_the_capacity_payload_is_valid_powershell(self):
        r = self._parse(fleet.CAPACITY_PS)
        self.assertEqual(r.returncode, 0,
                         f"CAPACITY_PS does not parse: {r.stdout}{r.stderr}")

    def test_the_parser_check_is_load_bearing(self):
        # Negative control. Without it, a parser invocation that silently did nothing
        # would make the test above pass for every possible payload, which is exactly
        # the vacuity the substring grep had.
        r = self._parse(fleet.CAPACITY_PS + "; if ($x { ")
        self.assertNotEqual(r.returncode, 0,
                            "a payload with an unbalanced brace was accepted — the "
                            "parser check proves nothing")
        self.assertIn("PARSE-ERROR", r.stdout)

    def test_every_runtime_probe_parses(self):
        for name, payload in fleet.RUNTIME_PROBES["powershell"].items():
            with self.subTest(runtime=name):
                r = self._parse(payload)
                self.assertEqual(r.returncode, 0,
                                 f"{name} probe does not parse: {r.stdout}{r.stderr}")

    def test_the_runtime_probes_run_and_answer_yes_or_no(self):
        """These ARE cross-platform (Get-Command), so execute them, do not just parse.

        A probe that emits nothing, or emits a PowerShell error object, reads to the
        fleet as an absent runtime rather than as a broken probe — the same
        indistinguishable-failure class again.
        """
        exe = self._pwsh()
        for name, payload in fleet.RUNTIME_PROBES["powershell"].items():
            with self.subTest(runtime=name):
                r = subprocess.run([exe, "-NoProfile", "-NonInteractive",
                                    "-Command", payload],
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, 0, f"{name} probe errored: {r.stderr}")
                self.assertIn(r.stdout.strip(), ("yes", "no"),
                              f"{name} probe answered {r.stdout.strip()!r}, which the "
                              f"fleet cannot read as a runtime verdict")


class PosixCapacity(unittest.TestCase):
    def test_memory_has_a_linux_fallback(self):
        # hw.memsize is macOS-only; without this a Linux node returned cores and load
        # but mem_gb=None -- a half-filled row that reads as a partly-broken machine.
        self.assertIn("hw.memsize", fleet.CAPACITY)
        self.assertIn("/proc/meminfo", fleet.CAPACITY)


class LocalOnlyNodes(unittest.TestCase):
    """host=None means "run it here", so a local_only node could impersonate its prober."""

    def test_cloud_is_registered_and_local_only(self):
        self.assertIn("cloud", fleet.NODES)
        self.assertTrue(fleet.NODES["cloud"].get("local_only"))
        self.assertIsNone(fleet.NODES["cloud"]["host"])

    def test_cloud_declares_no_runtimes(self):
        # Verified in a live container: no codex binary, no ~/.codex, no OpenRouter key.
        # The skill's rule is that a runtime is declared only after being watched
        # returning output. An entry here would be the wired-but-never-exercised bug.
        self.assertEqual(fleet.NODES["cloud"]["runtimes"], [])

    def test_probing_a_local_only_node_from_elsewhere_reports_unreachable(self):
        # THE regression. Without the guard, a probe from the MacBook runs CAPACITY on
        # the MacBook and prints the MacBook's cores under NODE=cloud. A map that
        # asserts where you are is worse than no map, because it is believed.
        original = fleet.LOCAL_NODE
        try:
            fleet.LOCAL_NODE = "macbook"
            row = fleet.probe_node("cloud")
            self.assertFalse(row["reachable"])
            self.assertIsNone(row["cores"], "cloud reported cores that belong to the prober")
            self.assertIn("local_only", row["notes"])
        finally:
            fleet.LOCAL_NODE = original

    def test_the_guard_is_load_bearing(self):
        # Negative control: with the guard bypassed, the impersonation really does
        # happen. A test that has never been observed failing guards nothing.
        original = fleet.LOCAL_NODE
        try:
            fleet.LOCAL_NODE = "macbook"
            saved = fleet.NODES["cloud"].pop("local_only")
            row = fleet.probe_node("cloud")
            fleet.NODES["cloud"]["local_only"] = saved
            self.assertTrue(
                row["reachable"] and row["cores"],
                "expected the unguarded path to measure the prober; if this stops "
                "happening the guard may no longer be what prevents it",
            )
        finally:
            fleet.LOCAL_NODE = original


class UnreachableRows(unittest.TestCase):
    def test_an_unreachable_node_still_reports_its_declared_runtimes(self):
        # Otherwise an offline node's row loses the one fact that does not depend on
        # reaching it, and the fleet table cannot be read while a machine is down.
        original = fleet.LOCAL_NODE
        try:
            fleet.LOCAL_NODE = "macbook"
            row = fleet.probe_node("cloud")
            self.assertIn("declared", row["runtimes"])
        finally:
            fleet.LOCAL_NODE = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
