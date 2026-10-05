#!/usr/bin/env python3
"""anchor.py is the only thing standing between /waterline and a self-blessed brief.

WHY. The skill hands adjudication to this script on purpose — "anchor.py decides what
anchored, not you" — so every rule it enforces is a rule no agent has to remember. That
makes it a control, and an untested control is the estate's dominant defect class: the
save-half works, the use-half never runs.

Three jobs, one test each, plus the negative controls that prove they can fail:

  ANCHOR  a claim absent from the challenged brief is discarded unread (t1)
  BIND    the ledger sha comes from the bytes on disk, so editing the brief voids
          the round it was cleared by (t5)
  STALL   a round that repeats the previous round's surviving claims stops the loop
          (t2), and a round that says something new does not (t3)

t2 IS A REGRESSION TEST, and it is the reason this file exists. The first version
compared this round's *anchored* claims against the previous round's *raw* claims —
including ones that round had already discarded as unanchored. Two byte-identical
rounds therefore scored 0.5 on a 0.82 threshold and reported `stalled=no`. The dilution
only happens when the challenger invents a claim, which is precisely the failure mode
the ANCHOR job exists for: the control went quiet in the one case it was written for.
Both sides must be anchored, or STALL is decorative.

Stdlib only, no pytest.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ANCHOR = Path(__file__).resolve().parents[1] / "scripts" / "anchor.py"

# Exit codes anchor.py contracts on. Named, because a bare 3 in an assert says nothing.
CLEAN, BLOCKED, NO_REPORT, STALLED = 0, 1, 2, 3


def finding(claim: str, severity: str = "P0") -> dict:
    return {"claim": claim, "severity": severity, "defect": "d", "fix": "f"}


def round_dir(parent: Path, name: str, brief: str, findings=None,
              unchallenged=("some boundary",)) -> Path:
    """Write one round's brief.md and report.json. findings=None writes no report."""
    d = parent / name
    d.mkdir(parents=True)
    (d / "brief.md").write_text(brief)
    if findings is not None:
        (d / "report.json").write_text(json.dumps({
            "verdict": "FAIL" if findings else "PASS",
            "blocking_findings": findings,
            "advisory_findings": [],
            "unchallenged": list(unchallenged),
            "independent_research": [],
        }))
    return d


def run(d: Path, prev: Path | None = None) -> tuple[int, str]:
    argv = [sys.executable, str(ANCHOR), str(d)] + ([str(prev)] if prev else [])
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


BRIEF = "The bar is p95 under 200ms on search.\nRollback is untested.\n"


def t1_unanchored_claim_is_discarded() -> None:
    """ANCHOR. A claim that is not verbatim in the brief never reaches the operator."""
    with tempfile.TemporaryDirectory() as tmp:
        r = round_dir(Path(tmp), "r1", BRIEF, [
            finding("Rollback is untested."),
            finding("The brief promises a 99.99% SLA."),   # never written; invented
        ])
        rc, out = run(r)
        assert "blocking_kept=1 blocking_discarded=1" in out, out
        assert "DISCARDED (unanchored)" in out and "99.99% SLA" in out, out
        assert "Rollback is untested." in out, out
        assert rc == BLOCKED, f"a surviving blocking finding must not exit clean (got {rc})"


def t2_stall_survives_a_discarded_claim() -> None:
    """STALL, the regression. Identical rounds must stall even when one claim was
    discarded — anchoring has to be applied to BOTH sides of the comparison."""
    with tempfile.TemporaryDirectory() as tmp:
        findings = [finding("Rollback is untested."),
                    finding("The brief promises a 99.99% SLA.")]
        prev = round_dir(Path(tmp), "r1", BRIEF, findings)
        now = round_dir(Path(tmp), "r2", BRIEF, findings)
        rc, out = run(now, prev)
        assert "stalled=yes" in out, (
            "two byte-identical rounds did not stall. The previous round's DISCARDED "
            f"claim is being counted against this round's anchored set:\n{out}")
        assert rc == STALLED, f"a stalled loop must exit {STALLED}, got {rc}"


def t3_a_new_finding_does_not_stall() -> None:
    """The negative control for t2. Without this, `stalled=yes` for everything passes t2."""
    with tempfile.TemporaryDirectory() as tmp:
        prev = round_dir(Path(tmp), "r1", BRIEF, [finding("Rollback is untested.")])
        now = round_dir(Path(tmp), "r2", BRIEF + "The cache is unbounded.\n",
                        [finding("The cache is unbounded.", "P1")])
        rc, out = run(now, prev)
        assert "stalled=no" in out, f"a round raising a new defect is progress, not a stall:\n{out}"
        assert rc == BLOCKED, f"got {rc}"


def t4_missing_report_is_not_a_pass() -> None:
    """Silence, timeout and crash are not clearances — rule 3 of the skill."""
    with tempfile.TemporaryDirectory() as tmp:
        r = round_dir(Path(tmp), "r1", BRIEF, None)
        rc, out = run(r)
        assert "verdict=NO_VERDICT" in out, out
        assert rc == NO_REPORT, f"an absent report must never exit clean (got {rc})"


def t5_editing_the_brief_changes_the_binding() -> None:
    """BIND. The report is bound to the exact bytes challenged."""
    with tempfile.TemporaryDirectory() as tmp:
        r = round_dir(Path(tmp), "r1", BRIEF, [finding("Rollback is untested.")])
        before = run(r)[1].split("brief_sha256=")[1].split()[0]
        (r / "brief.md").write_text(BRIEF + "a paragraph added after clearance\n")
        after = run(r)[1].split("brief_sha256=")[1].split()[0]
        assert before != after, (
            f"the brief changed and the ledger sha did not ({before}) — a stale PASS "
            "would still look bound to the edited brief")


def t6_lazy_clean_pass_is_flagged() -> None:
    """The observed opening move is a PASS with empty arrays. It must not read as coverage."""
    with tempfile.TemporaryDirectory() as tmp:
        r = round_dir(Path(tmp), "r1", BRIEF, [], unchallenged=())
        rc, out = run(r)
        assert "WARNING" in out and "unchallenged" in out, out
        assert rc == CLEAN, f"a clean round is still clean, just noisy (got {rc})"


TESTS = (
    t1_unanchored_claim_is_discarded,
    t2_stall_survives_a_discarded_claim,
    t3_a_new_finding_does_not_stall,
    t4_missing_report_is_not_a_pass,
    t5_editing_the_brief_changes_the_binding,
    t6_lazy_clean_pass_is_flagged,
)


def main() -> int:
    failures = []
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failures.append(t.__name__)
    n = len(TESTS)
    print(f"\n{n - len(failures)}/{n} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
