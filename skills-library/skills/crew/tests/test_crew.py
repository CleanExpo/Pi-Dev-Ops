#!/usr/bin/env python3
"""Controls for the /crew evidence log, renderer and preflight gate.

Every control here answers "will this fire when the defect is present". The three that guard
a challenged finding -- concurrent appends, the optional Pi-CEO mirror, and absent-is-not-
broken -- each have a companion mutation test in mutate_crew.py that reintroduces the defect
and asserts the control goes red. A control that has never been red is not evidence.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import crew_log        # noqa: E402
import crew_preflight  # noqa: E402


class LogConcurrency(unittest.TestCase):
    def test_concurrent_writers_lose_no_lines(self):
        """N processes appending at once: every line lands, every line parses.

        This is the shape that fails silently -- interleaved writes produce a file that is
        the right size and the wrong content, so the assertion is on parseability per line,
        not just line count.

        The payload is deliberately large. A short record goes out in one atomic O_APPEND
        write and survives even with the lock removed, so a small-payload version of this
        test passes under its own mutant and proves nothing. Evidence fields legitimately
        carry diffs and captured tool output, so a record big enough to be torn is the
        realistic case, and it is the only one that actually exercises the lock.
        """
        writers, per_writer, pad = 16, 8, 300_000
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "runs.jsonl"
            prog = (
                "import sys; sys.path.insert(0, %r);"
                "import crew_log, pathlib;"
                "crew_log.PRIMARY = pathlib.Path(%r);"
                "crew_log.MIRROR_DIR = pathlib.Path(%r);"
                "[crew_log.emit({'type':'tool','actor_role':'w'+sys.argv[1],"
                "'session_id':'s','fields':{'i':str(i),'pad':'x'*%d}}) for i in range(%d)]"
                % (str(SCRIPTS), str(target), str(Path(td) / "nope"), pad, per_writer)
            )
            procs = [subprocess.Popen([sys.executable, "-c", prog, str(n)])
                     for n in range(writers)]
            for p in procs:
                self.assertEqual(p.wait(timeout=120), 0)

            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), writers * per_writer,
                             "line count != writes issued — appends were lost or split")
            for ln in lines:
                json.loads(ln)  # raises on an interleaved/torn line


class MirrorIsOptionalAndNeverCreated(unittest.TestCase):
    def test_mirror_written_when_dir_exists(self):
        with tempfile.TemporaryDirectory() as td:
            primary = Path(td) / "runs.jsonl"
            mirror_dir = Path(td) / "swarm"
            mirror_dir.mkdir()
            crew_log.PRIMARY, crew_log.MIRROR_DIR = primary, mirror_dir
            crew_log.MIRROR = mirror_dir / "runs.jsonl"
            status = crew_log.emit({"type": "run_start", "session_id": "s"})
            self.assertTrue(status["mirrored"])
            self.assertEqual(len((mirror_dir / "runs.jsonl").read_text().splitlines()), 1)

    def test_mirror_skipped_and_dir_not_created_when_absent(self):
        """The disputed finding, settled: absent means skip, not create, not fail."""
        with tempfile.TemporaryDirectory() as td:
            primary = Path(td) / "runs.jsonl"
            mirror_dir = Path(td) / "no-pi-ceo-on-this-machine"
            crew_log.PRIMARY, crew_log.MIRROR_DIR = primary, mirror_dir
            crew_log.MIRROR = mirror_dir / "runs.jsonl"
            status = crew_log.emit({"type": "run_start", "session_id": "s"})
            self.assertFalse(status["mirrored"])
            self.assertEqual(status["mirror_skipped_reason"], "absent")
            self.assertFalse(mirror_dir.exists(),
                             "mirror directory was created — that fabricates harness state")
            # The primary log is unaffected: a missing mirror is not a failed run.
            self.assertEqual(len(primary.read_text().splitlines()), 1)


def _render(args, log_path):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "crew_render.py"), "--log", str(log_path)] + args,
        capture_output=True, text=True)


class AbsentIsNotBroken(unittest.TestCase):
    """Three empty-looking states must be distinguishable, or the render lies by omission."""

    def test_missing_log_says_so(self):
        with tempfile.TemporaryDirectory() as td:
            r = _render([], Path(td) / "nothing.jsonl")
            self.assertEqual(r.returncode, 2)
            self.assertIn("NO LOG", r.stderr)

    def test_empty_log_is_distinct_from_missing_log(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runs.jsonl"
            p.write_text("")
            r = _render([], p)
            self.assertEqual(r.returncode, 2)
            self.assertIn("LOG EMPTY", r.stderr)
            self.assertNotIn("NO LOG", r.stderr)

    def test_unknown_session_is_distinct_from_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runs.jsonl"
            p.write_text(json.dumps({"ts": "2026-08-10T21:00:00+1000", "type": "run_start",
                                     "actor_role": None, "session_id": "real",
                                     "fields": {}}) + "\n")
            r = _render(["--session", "ghost"], p)
            self.assertEqual(r.returncode, 2)
            self.assertIn("NOT FOUND", r.stderr)
            self.assertIn("real", r.stderr)

    def test_present_run_renders_and_absent_role_reads_as_not_dispatched(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runs.jsonl"
            rows = [
                {"ts": "2026-08-10T21:00:00+1000", "type": "run_start", "actor_role": None,
                 "session_id": "s1", "fields": {"task": "t", "grounding": "DEGRADED (619)"}},
                {"ts": "2026-08-10T21:00:05+1000", "type": "done", "actor_role": "scout",
                 "session_id": "s1", "fields": {"note": "mapped"}},
            ]
            p.write_text("".join(json.dumps(r) + "\n" for r in rows))
            r = _render(["--session", "s1"], p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("scout", r.stdout)
            self.assertIn("DEGRADED (619)", r.stdout)
            # planner never ran: it must be visibly absent, not silently omitted.
            self.assertRegex(r.stdout, r"planner\s+not dispatched")

    def test_malformed_lines_are_reported_not_swallowed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runs.jsonl"
            p.write_text('{"ts":"2026-08-10T21:00:00+1000","type":"run_start",'
                         '"session_id":"s1","fields":{}}\n'
                         "{ this is not json\n")
            r = _render(["--session", "s1"], p)
            self.assertEqual(r.returncode, 0)
            self.assertIn("1 malformed", r.stderr)


class RiskTierGate(unittest.TestCase):
    # The drift entry carries a risk_tier_ceiling on purpose. With only a sha256 there, a
    # parser that fails to end the agents block still yields the right answer by luck --
    # roles are only recorded on a ceiling line -- so the fixture would pass under its own
    # mutant. This shape is what actually distinguishes a scoped parser from a greedy one.
    REG = """version: 1
agents:
  - id: scout
    risk_tier_ceiling: 0
  - id: builder
    risk_tier_ceiling: 1
accepted_projection_drift:
  - id: judge
    agents_sha256: deadbeef
    risk_tier_ceiling: 3
"""

    def _roles(self, text):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.yaml"
            p.write_text(text)
            return crew_preflight.load_registry(p)

    def test_reads_only_the_agents_block(self):
        roles = self._roles(self.REG)
        self.assertEqual(roles, {"scout": 0, "builder": 1})
        self.assertNotIn("judge", roles,
                         "accepted_projection_drift ids must not become dispatchable roles")

    def test_within_ceiling_allowed(self):
        ok, _ = crew_preflight.check_role("builder", 1, self._roles(self.REG))
        self.assertTrue(ok)

    def test_above_ceiling_refused(self):
        ok, why = crew_preflight.check_role("scout", 1, self._roles(self.REG))
        self.assertFalse(ok)
        self.assertIn("ceiling", why)

    def test_unknown_role_refused(self):
        ok, _ = crew_preflight.check_role("smuggled", 0, self._roles(self.REG))
        self.assertFalse(ok)

    def test_empty_registry_refuses_everything(self):
        """Fail closed: an unreadable registry must not read as 'no restrictions'."""
        ok, why = crew_preflight.check_role("scout", 0, {})
        self.assertFalse(ok)
        self.assertIn("refusing", why)

    def test_missing_registry_file_yields_no_roles(self):
        self.assertEqual(crew_preflight.load_registry(Path("/nonexistent/registry.yaml")), {})

    def test_quoted_ids_resolve(self):
        """YAML allows `id: "scout"`. Captured raw, the quotes join the key and every lookup
        misses -- fail-closed, but it makes the entire crew silently undispatchable."""
        roles = self._roles('version: 1\nagents:\n'
                            '  - id: "scout"\n    risk_tier_ceiling: 0\n'
                            "  - id: 'builder'\n    risk_tier_ceiling: 1\n")
        self.assertEqual(roles, {"scout": 0, "builder": 1})
        ok, _ = crew_preflight.check_role("scout", 0, roles)
        self.assertTrue(ok)

    def test_unbalanced_quote_does_not_resolve_to_a_real_role(self):
        roles = self._roles('version: 1\nagents:\n  - id: "scout\n    risk_tier_ceiling: 0\n')
        self.assertNotIn("scout", roles)


class BrainJsResolution(unittest.TestCase):
    def test_only_known_vault_names_are_searched(self):
        """A bare ~/2nd* glob would run brain.js out of any directory starting with '2nd'."""
        self.assertEqual(crew_preflight.VAULT_DIRS, ("2nd Brain", "2nd-brain"))

    def test_resolves_on_this_machine(self):
        self.assertIsNotNone(crew_preflight.find_brain_js())


class LogFailureIsLoud(unittest.TestCase):
    def test_cli_reports_a_lost_record_instead_of_a_traceback(self):
        """A dropped evidence record must exit non-zero with a legible reason: a caller that
        reads a traceback as 'crashed' may retry, but one that reads exit 0 assumes it
        landed."""
        with tempfile.TemporaryDirectory() as td:
            # Redirect HOME, then put a FILE where the log's parent directory must be, so
            # mkdir(parents=True) raises. This drives the real CLI failure path rather than
            # asserting a range of acceptable exit codes, which would assert nothing.
            state = Path(td) / ".claude" / "state"
            state.mkdir(parents=True)
            (state / "crew").write_text("not a directory")
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "crew_log.py"), "--type", "t",
                 "--session", "s"],
                capture_output=True, text=True, env=dict(os.environ, HOME=td))
            self.assertEqual(r.returncode, 1, f"expected a clean failure, got {r.stdout!r}")
            self.assertIn('"written": false', r.stderr.lower())
            self.assertNotIn("Traceback", r.stderr)

    def test_emit_raises_rather_than_silently_dropping(self):
        with tempfile.TemporaryDirectory() as td:
            blocked = Path(td) / "runs.jsonl"
            blocked.mkdir()
            crew_log.PRIMARY = blocked
            crew_log.MIRROR_DIR = Path(td) / "absent"
            with self.assertRaises(OSError):
                crew_log.emit({"type": "t", "session_id": "s"})


class GroundingStamp(unittest.TestCase):
    def test_stamp_is_one_of_the_known_states(self):
        stamp, detail = crew_preflight.grounding_status()
        self.assertIn(stamp, {"OK", "DEGRADED", "UNAVAILABLE"})
        self.assertTrue(detail)

    def test_brain_js_resolves_on_this_machine(self):
        """Guards the machine-specific-path failure the estate has hit before."""
        self.assertIsNotNone(crew_preflight.find_brain_js())


if __name__ == "__main__":
    unittest.main(verbosity=2)
