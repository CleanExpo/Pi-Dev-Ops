#!/usr/bin/env python3
"""Behavioural controls for 04_evidence_gate.py and its installer.

Deliberately relocatable: every path is resolved relative to this file, so the
suite runs correctly from a COPY of skills/forge/ outside the repo. That is how
skills/enforcement-loop/install/positive_control.py sabotages it — a suite that
only works in situ cannot be proven able to fail. The repo-rooted drift check
lives in check_copies_in_step.py for exactly this reason.

Every test here is a control in the strict sense: it asserts the guard FIRES on a
planted defect, not merely that a clean run stays quiet. A gate that returns zero
on everything passes a suite built only from happy paths, which is how the three
silent fail-opens this file now covers survived for months.

Stdlib only, no network, no writes outside a temp dir. Run:
    python3 skills/forge/tests/test_evidence_gate.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(os.path.dirname(HERE), "install")
GATE = os.path.join(INSTALL, "04_evidence_gate.py")
INSTALLER = os.path.join(INSTALL, "install-evidence-gate.py")
DEP = os.path.join(INSTALL, "hook_failure.py")

CLAIM = "All tests pass and the task is complete."


def transcript(path, with_tool_use):
    """A minimal turn: one user message, then the assistant's reply."""
    lines = [{"type": "user", "message": {"role": "user", "content": "is it done?"}}]
    if with_tool_use:
        lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}})
        lines.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
    lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": CLAIM}]}})
    with open(path, "w", encoding="utf-8") as f:
        for e in lines:
            f.write(json.dumps(e) + "\n")
    return path


def run_gate(payload, home, env_extra=None):
    env = dict(os.environ, HOME=home)
    env.pop("SKIP_EVIDENCE_GATE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, GATE], input=payload,
                          capture_output=True, text=True, timeout=30, env=env)


class GateBehaviour(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_blocks_completion_claim_with_zero_tool_use(self):
        """The defect the gate exists for. If this stops failing, the gate is dead."""
        t = transcript(os.path.join(self.tmp, "t.jsonl"), with_tool_use=False)
        out = run_gate(json.dumps({"transcript_path": t}), self.tmp).stdout
        self.assertIn('"decision": "block"', out)

    def test_allows_same_claim_when_the_turn_used_a_tool(self):
        """Negative control: without this, a gate that blocks everything would pass above."""
        t = transcript(os.path.join(self.tmp, "t.jsonl"), with_tool_use=True)
        self.assertEqual(run_gate(json.dumps({"transcript_path": t}), self.tmp).stdout.strip(), "")

    def test_the_payload_reply_wins_over_a_stale_transcript_tail(self):
        """Stop's last_assistant_message is the reply being judged; the transcript tail can lag."""
        t = transcript(os.path.join(self.tmp, "t.jsonl"), with_tool_use=False)
        payload = {"transcript_path": t, "last_assistant_message": "Here is the plan for tomorrow."}
        self.assertEqual(run_gate(json.dumps(payload), self.tmp).stdout.strip(), "")

    def test_unreadable_stdin_announces(self):
        out = run_gate("not json", self.tmp).stdout
        self.assertIn("DID NOT RUN", out)

    def test_absent_transcript_path_announces(self):
        out = run_gate("{}", self.tmp).stdout
        self.assertIn("transcript_path absent", out)

    def test_missing_transcript_file_announces(self):
        out = run_gate(json.dumps({"transcript_path": "/nonexistent/x.jsonl"}), self.tmp).stdout
        self.assertIn("transcript file does not exist", out)

    def test_stop_hook_active_stays_silent(self):
        """Must never double-fire inside one stop cycle."""
        self.assertEqual(run_gate(json.dumps({"stop_hook_active": True}), self.tmp).stdout.strip(), "")

    def test_skip_env_var_no_longer_switches_the_gate_off(self):
        """The SKIP_EVIDENCE_GATE=1 escape hatch was removed; prove it is inert.

        An environment variable proves nothing about WHO set it: any process, script
        or agent inside the session could set it, and the gate then returned silently,
        so a disabled gate was byte-identical to a clean pass. Filed P1 by independent
        review 2026-08-29 and removed from hooks/Stop/04_evidence_gate.py the same day
        -- but the removal did not reach this installer copy for three days, and this
        suite went on pinning the bypass as correct behaviour. check_copies_in_step.py
        is what found the fork; without it the two copies would still disagree.

        Asserts on the block DECISION rather than on silence. A gate that crashed at
        import is also silent, so silence can never tell a working gate from a dead
        one -- the same defect class this whole file exists for.
        """
        t = transcript(os.path.join(self.tmp, "t.jsonl"), with_tool_use=False)
        out = run_gate(json.dumps({"transcript_path": t}), self.tmp,
                       {"SKIP_EVIDENCE_GATE": "1"}).stdout
        self.assertIn('"decision": "block"', out)

    def test_failures_reach_a_durable_log_not_just_stderr(self):
        r = run_gate("not json", self.tmp)
        self.assertNotIn("no-module", r.stderr)  # the real module, not the fallback shim
        log = os.path.join(self.tmp, "Pi-CEO", ".harness", "swarm", "hook-failures.jsonl")
        self.assertTrue(os.path.exists(log), "no durable record written")
        self.assertIn("04_evidence_gate", open(log, encoding="utf-8").read())


class ReporterCannotKillTheHook(unittest.TestCase):
    """Regression for the P1 found by independent review 2026-08-29.

    record_failure/record_skip run BEFORE the gate prints its fail-open
    systemMessage. Their last-resort diagnostic went to stderr unguarded, so with the
    durable log unwritable AND stderr closed the reporter raised, killing the hook
    before the operator was ever told the gate did not run — the exact silent failure
    the whole change set is about, reintroduced one layer down.
    """

    def run_with_stderr_closed(self, home):
        # HOME points at a regular file, so the logger's mkdir fails and the stderr
        # fallback is reached; fd 2 is closed, so an unguarded write there raises.
        env = dict(os.environ, HOME=home)
        env.pop("SKIP_EVIDENCE_GATE", None)
        return subprocess.run([sys.executable, GATE], input="{}", capture_output=True,
                              text=True, timeout=30, env=env,
                              preexec_fn=lambda: os.close(2))

    def test_reporters_survive_an_argument_whose_repr_raises(self):
        """Regression for the P1 found by independent review 2026-08-29.

        record_failure built its record by evaluating repr(exc) in the caller's frame,
        so an exception whose __repr__ raised escaped before _write was entered — past
        every guard inside it. The same shape existed in the gate's fallback shims,
        which formatted their f-string at the call site. Both reporters must be total:
        nothing handed to them can make them raise.
        """
        script = (
            "import sys\n"
            f"sys.path.insert(0, {INSTALL!r})\n"
            "import hook_failure\n"
            "class Nasty(Exception):\n"
            "    def __repr__(self): raise RuntimeError('repr exploded')\n"
            "    def __str__(self): raise RuntimeError('str exploded')\n"
            "hook_failure.record_failure('h', 'w', Nasty(), Nasty())\n"
            "hook_failure.record_skip('h', Nasty())\n"
            "print('SURVIVED')\n"
        )
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                           text=True, timeout=30, env=dict(os.environ, HOME=home))
        self.assertIn("SURVIVED", r.stdout,
                      f"a reporter raised on a hostile argument: {r.stderr!r}")

    def test_gate_still_announces_when_logging_and_stderr_both_fail(self):
        fd, blocker = tempfile.mkstemp()  # a FILE where a home directory is expected
        os.close(fd)
        self.addCleanup(os.unlink, blocker)
        r = self.run_with_stderr_closed(blocker)
        self.assertEqual(r.returncode, 0, f"reporter took the hook down: {r.stderr!r}")
        self.assertIn("DID NOT RUN", r.stdout,
                      "operator notification was lost when the reporter failed")


class InstallerProbe(unittest.TestCase):
    """The installer must refuse to register a gate whose reporter is broken."""

    def sandbox(self, with_dep):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        dst = os.path.join(home, ".claude", "skills", "forge", "install")
        os.makedirs(dst)
        shutil.copyfile(GATE, os.path.join(dst, "04_evidence_gate.py"))
        shutil.copyfile(INSTALLER, os.path.join(dst, "install-evidence-gate.py"))
        if with_dep:
            shutil.copyfile(DEP, os.path.join(dst, "hook_failure.py"))
        with open(os.path.join(home, ".claude", "settings.json"), "w") as f:
            json.dump({"hooks": {"Stop": [{"hooks": []}]}}, f)
        return home, os.path.join(dst, "install-evidence-gate.py")

    def install(self, home, script, env_extra=None):
        env = dict(os.environ, HOME=home)
        env.pop("SKIP_EVIDENCE_GATE", None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run([sys.executable, script], capture_output=True, text=True,
                              timeout=60, env=env)

    def registered(self, home):
        with open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8") as f:
            s = json.load(f)
        return [h["command"] for h in s["hooks"]["Stop"][0]["hooks"]]

    def test_clean_install_succeeds_and_registers(self):
        home, script = self.sandbox(with_dep=True)
        self.assertEqual(self.install(home, script).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(home, ".claude", "hooks", "hook_failure.py")))
        self.assertTrue(any("04_evidence_gate.py" in c for c in self.registered(home)))

    def test_rerun_is_idempotent(self):
        home, script = self.sandbox(with_dep=True)
        self.install(home, script)
        self.assertEqual(self.install(home, script).returncode, 0)
        self.assertEqual(len([c for c in self.registered(home) if "04_evidence_gate.py" in c]), 1)

    def test_missing_dependency_refuses_to_register(self):
        home, script = self.sandbox(with_dep=False)
        self.assertEqual(self.install(home, script).returncode, 1)
        self.assertEqual(self.registered(home), [])

    def test_gate_that_never_reaches_main_is_rejected(self):
        """Regression for the P1 found by independent review 2026-08-29.

        The probe used to treat absence of the fallback markers as success. A gate
        that dies before main() — SystemExit at import, a crash, a signal — also
        emits no markers, so it read as a pass. Absence of a bad sign is not a good
        sign; success must require a positive execution sentinel.
        """
        home, script = self.sandbox(with_dep=True)
        # Exits 0, writes nothing, never reaches main(). Empty stderr, no markers.
        gate = os.path.join(home, ".claude", "skills", "forge", "install",
                            "04_evidence_gate.py")
        with open(gate, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(0)\n")
        r = self.install(home, script)
        self.assertEqual(r.returncode, 1, "silent-death gate passed the probe")
        self.assertIn("sentinel", r.stdout)
        self.assertEqual(self.registered(home), [])

    def test_failed_upgrade_does_not_clobber_a_working_gate(self):
        """Regression for the P1 found by independent review 2026-08-29.

        The installer copied over the live gate BEFORE probing it, so a failed
        upgrade returned 1 having already replaced a working hook with the broken
        candidate, which stayed registered and active. Fresh-install tests cannot see
        this: on a fresh install there is nothing to clobber.
        """
        home, script = self.sandbox(with_dep=True)
        self.assertEqual(self.install(home, script).returncode, 0)
        installed = os.path.join(home, ".claude", "hooks", "Stop", "04_evidence_gate.py")
        good = open(installed, "rb").read()
        registered_before = self.registered(home)

        # Now break the SOURCE and re-run, as a bad upgrade would.
        src = os.path.join(home, ".claude", "skills", "forge", "install")
        with open(os.path.join(src, "04_evidence_gate.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(3)\n")
        r = self.install(home, script)

        self.assertEqual(r.returncode, 1, "broken upgrade was accepted")
        self.assertEqual(open(installed, "rb").read(), good,
                         "a failed upgrade overwrote the working gate")
        self.assertEqual(self.registered(home), registered_before)

    def test_upgrade_replaces_the_gate_rather_than_truncating_it(self):
        """Regression for the P1 found by independent review 2026-08-29.

        Installation used shutil.copyfile, which opens the live destination for
        truncating replacement — an interruption mid-write leaves the registered gate
        empty or half-written, silently disabling an enforcement hook.

        Atomicity itself cannot be simulated here, but the mechanism is observable:
        os.replace swaps in a new file, so the destination's INODE changes across an
        upgrade. copyfile writes through the existing inode and leaves it unchanged.
        Asserting only byte-completeness would pass on both implementations and prove
        nothing; the inode is what distinguishes them.
        """
        home, script = self.sandbox(with_dep=True)
        self.assertEqual(self.install(home, script).returncode, 0)
        hooks = os.path.join(home, ".claude", "hooks")
        installed = os.path.join(hooks, "Stop", "04_evidence_gate.py")
        first_inode = os.stat(installed).st_ino

        # A real content change, still a valid gate, so the second run genuinely copies.
        src_gate = os.path.join(home, ".claude", "skills", "forge", "install",
                                "04_evidence_gate.py")
        with open(src_gate, "a", encoding="utf-8") as f:
            f.write("\n# upgraded\n")
        self.assertEqual(self.install(home, script).returncode, 0)

        self.assertNotEqual(os.stat(installed).st_ino, first_inode,
                            "gate was written through the existing inode (truncating "
                            "in place), not atomically replaced")
        self.assertEqual(open(installed, "rb").read(), open(src_gate, "rb").read(),
                         "upgraded gate did not land byte-complete")
        leaked = [p for d in (hooks, os.path.join(hooks, "Stop"))
                  for p in os.listdir(d) if p.startswith(".install-tmp-")]
        self.assertEqual(leaked, [], f"temp siblings leaked: {leaked}")

    def test_ambient_module_does_not_satisfy_a_missing_dependency(self):
        """Regression for the P1 found by independent review 2026-08-29.

        A missing DEP_SRC used to warn and let the probe decide. But the probe only
        proves hook_failure was IMPORTABLE, and after <stage> the interpreter searches
        the rest of sys.path — so a same-named module on PYTHONPATH, in site-packages,
        or in the working directory satisfied both the import and the sentinel. The
        installer then registered a gate whose reporter came from somewhere it never
        declared and might not exist on the next run.

        This also repairs test_missing_dependency_refuses_to_register, which passed
        only because no ambient hook_failure happened to exist in the test
        environment — a control that would have stopped discriminating the moment one
        did, without anything going red.
        """
        home, script = self.sandbox(with_dep=False)
        ambient = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, ambient, ignore_errors=True)
        with open(os.path.join(ambient, "hook_failure.py"), "w", encoding="utf-8") as f:
            f.write("def record_failure(*a, **k):\n    pass\n"
                    "def record_skip(*a, **k):\n    pass\n")

        r = self.install(home, script, {"PYTHONPATH": ambient})
        self.assertEqual(r.returncode, 1,
                         "an ambient hook_failure satisfied a missing dependency")
        self.assertIn("required dependency missing", r.stdout)
        self.assertEqual(self.registered(home), [])
        self.assertFalse(os.path.exists(os.path.join(home, ".claude", "hooks", "Stop",
                                                     "04_evidence_gate.py")))

    def test_ambient_bypass_cannot_make_the_probe_misjudge_the_gate(self):
        """Descendant of test_probe_is_not_disarmed_by_the_gates_own_bypass.

        History, because the name changed and the thing it guards moved. The original
        P1 (independent review, 2026-08-29) was that SKIP_EVIDENCE_GATE=1 in the
        INSTALLER's environment was inherited by the probe's subprocess, so the gate
        returned before touching hook_failure, the run came back empty, and a broken
        import read as a pass. It was closed by stripping the variable in probe().

        On 29/08/2026 the escape hatch was removed from the gate itself, which made
        that strip inert: positive_control.py demonstrated the point by disarming the
        strip and watching this suite stay GREEN. A test that cannot fail is worse
        than no test, so the strip is gone and this assertion has been re-aimed.

        What it proves now is the same property from the installer's side, and it is
        NOT vacuous: with no filter in probe(), a gate that honoured the variable again
        would return silently under this environment, emit no sentinel, and the install
        would fail. Install SUCCESS while the bypass is set is therefore evidence that
        the gate ignores it end to end -- through /usr/bin/env python3, in a subprocess,
        with the variable genuinely present. The direct control on the gate's own stdout
        is test_skip_env_var_no_longer_switches_the_gate_off.
        """
        home, script = self.sandbox(with_dep=True)
        r = self.install(home, script, {"SKIP_EVIDENCE_GATE": "1"})
        self.assertEqual(r.returncode, 0,
                         f"an ambient SKIP_EVIDENCE_GATE broke the install: {r.stdout!r}")
        self.assertTrue(any("04_evidence_gate.py" in c for c in self.registered(home)))


if __name__ == "__main__":
    # Results go to STDOUT, not unittest's default stderr. positive_control.py
    # greps stdout for the test that caught each sabotage; on stderr every forge
    # sabotage reported "went red, but <test> was not what caught it" — the
    # control could not attribute the failure and read as broken. The other
    # suites in this workflow already print to stdout.
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    unittest.main(testRunner=runner)
