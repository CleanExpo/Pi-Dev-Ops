#!/usr/bin/env python3
"""Mutation controls for the /crew suite.

Each entry reintroduces one defect into a THROWAWAY COPY of the skill and asserts that the
control guarding it goes red. A control that has never been red is not evidence -- the
estate has shipped a green suite over an unreachable code path before, and this file is the
answer to that.

The source tree is never modified. Every mutation is applied to a copy under a temporary
directory, which is deleted whether or not the run succeeds.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

MUTANTS = [
    {
        # Removing the lock ALONE is not detectable here and the harness must not pretend
        # otherwise: on APFS a single O_APPEND write of 300 KB still lands intact. What the
        # concurrency control actually guards is the append STRATEGY, so the mutant is the
        # realistic wrong implementation -- seek-to-end then write, with no lock and no
        # O_APPEND. That is a read-modify-write race and it tears under load.
        "name": "unsafe append: seek-to-end + write, no lock, no O_APPEND",
        "file": "scripts/crew_log.py",
        "old": "    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)",
        "new": "    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)\n"
               "    os.lseek(fd, 0, os.SEEK_END)\n"
               "    time.sleep(0.001)",
        "guards": "LogConcurrency",
    },
    {
        "name": "partial writes ignored (single unchecked os.write)",
        "file": "scripts/crew_log.py",
        "old": "            written = 0\n"
               "            while written < len(payload):\n"
               "                n = os.write(fd, payload[written:])\n"
               "                if n <= 0:\n"
               "                    raise OSError(f\"append to {path} stalled after "
               "{written} bytes\")\n"
               "                written += n",
        "new": "            os.write(fd, payload)",
        "guards": "LogConcurrency",
        "expect_survivable": True,
        "why_survivable": "a short write on a regular APFS file cannot be provoked from "
                          "userspace; the loop is correctness insurance, not a tested path",
    },
    {
        "name": "mirror directory created when absent",
        "file": "scripts/crew_log.py",
        "old": "    if MIRROR_DIR.is_dir():",
        "new": "    MIRROR_DIR.mkdir(parents=True, exist_ok=True)\n    if MIRROR_DIR.is_dir():",
        "guards": "MirrorIsOptionalAndNeverCreated",
    },
    {
        "name": "renderer collapses a missing log into the empty-log message",
        "file": "scripts/crew_render.py",
        "old": '        print(f"NO LOG at {path}", file=sys.stderr)',
        "new": '        print(f"LOG EMPTY at {path}", file=sys.stderr)',
        "guards": "AbsentIsNotBroken",
    },
    {
        "name": "risk gate defaults to allow when the registry is unreadable",
        "file": "scripts/crew_preflight.py",
        "old": '    if not roles:\n        return False, "registry unreadable or empty '
               '— refusing every role"',
        "new": '    if not roles:\n        return True, "registry unreadable — allowing"',
        "guards": "RiskTierGate",
    },
    {
        "name": "quoted registry ids keep their quotes",
        "file": "scripts/crew_preflight.py",
        "old": "            for q in ('\"', \"'\"):",
        "new": "            for q in ():",
        "guards": "RiskTierGate",
    },
    {
        "name": "brain.js resolved by a bare ~/2nd* glob",
        "file": "scripts/crew_preflight.py",
        "old": 'VAULT_DIRS = ("2nd Brain", "2nd-brain")',
        "new": 'VAULT_DIRS = tuple(p.name for p in Path.home().glob("2nd*"))',
        "guards": "BrainJsResolution",
    },
    {
        "name": "log CLI lets the failure escape as a traceback",
        "file": "scripts/crew_log.py",
        "old": "    except (TimeoutError, OSError) as exc:",
        "new": "    except (TimeoutError,) as exc:",
        "guards": "LogFailureIsLoud",
    },
    {
        "name": "registry parser also reads accepted_projection_drift ids",
        "file": "scripts/crew_preflight.py",
        "old": '        if in_agents and re.match(r"^[A-Za-z_]", raw):\n'
               '            in_agents = False',
        "new": "        pass",
        "guards": "RiskTierGate",
    },
]


def run_suite(tree: Path, klass: str = ""):
    """Run the suite, or just one class of it. An empty klass means the whole suite --
    unittest reads a bare '' as a test name and errors, so it must be omitted entirely."""
    cmd = [sys.executable, str(tree / "tests" / "test_crew.py")]
    if klass:
        cmd.append(klass)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def main() -> int:
    failures = []
    killed_classes = set()
    declared = []

    baseline = run_suite(SKILL)
    if baseline.returncode != 0:
        print("ABORT: the unmutated suite is not green; fix that before trusting mutations")
        print(baseline.stdout[-2000:], baseline.stderr[-2000:])
        return 2
    print("baseline: unmutated suite is green\n")

    for m in MUTANTS:
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td) / "crew"
            shutil.copytree(SKILL, tree)
            target = tree / m["file"]
            src = target.read_text(encoding="utf-8")
            if m["old"] not in src:
                print(f"ABORT: anchor not found for mutant {m['name']!r} in {m['file']}")
                return 2
            target.write_text(src.replace(m["old"], m["new"], 1), encoding="utf-8")

            res = run_suite(tree, m["guards"])
            if res.returncode == 0:
                if m.get("expect_survivable"):
                    # Declared, not discovered. Validated after the loop, not here: judging it
                    # inline would depend on mutant ORDER, so moving the declaration above its
                    # killed sibling would silently change the verdict.
                    declared.append(m)
                    continue
                print(f"  NOT DETECTED  {m['name']}")
                print(f"                {m['guards']} stayed green under the defect")
                failures.append(m["name"])
            else:
                first = ""
                for line in (res.stderr or "").splitlines():
                    if line.startswith(("FAIL:", "ERROR:")):
                        first = line
                        break
                killed_classes.add(m["guards"])
                print(f"  detected      {m['name']}")
                if first:
                    print(f"                -> {first}")

    # A survivable declaration is not self-certifying. Left unchecked it would let a genuinely
    # dead control be waved through by labelling its only mutant survivable, so a declaration
    # holds ONLY while some OTHER mutant of the same guard class was killed this run. That
    # keeps the class provably alive and narrows the declaration to the one path that cannot
    # be provoked, rather than excusing the whole control.
    for m in declared:
        if m["guards"] not in killed_classes:
            print(f"  INVALID       {m['name']}")
            print(f"                declared survivable, but no other mutant of "
                  f"{m['guards']} was killed — that class is unproven")
            failures.append(m["name"] + " (unproven survivable declaration)")
        else:
            print(f"  SURVIVES      {m['name']}  (declared; {m['guards']} proven "
                  f"live by another mutant)")
            print(f"                {m['why_survivable']}")

    print()
    if failures:
        print(f"{len(failures)} mutant(s) survived — those controls cannot fail")
        return 1
    print(f"all {len(MUTANTS) - len(declared)} killable mutants detected"
          + (f"; {len(declared)} declared survivable and validated" if declared else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
