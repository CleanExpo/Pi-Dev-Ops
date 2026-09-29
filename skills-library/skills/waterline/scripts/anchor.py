#!/usr/bin/env python3
"""Evaluate one challenge round. anchor.py <round-dir> [prev-round-dir]

Three jobs, all mechanical, because a rule an agent must remember is not a control:

1. ANCHOR   Every finding's `claim` must appear verbatim in the brief that was actually
            challenged. A finding that does not anchor is DISCARDED UNREAD. Measured
            failure mode, not paranoia: a fallback reviewer once attributed a real line to
            the wrong file and reported a branch's own fix as the defect.
2. BIND     brief_sha256 is computed HERE from the bytes on disk, never asked of the model
            (it would guess). A report is valid only for the brief it was given; revise the
            brief and the previous PASS is void.
3. STALL    Compare this round's surviving claims with the previous round's. Substantial
            repetition means the loop is not converging — stop rather than spend a round.

Prints a ledger row, then the surviving findings. Exit 0 = no blocking findings survive.
"""
import hashlib
import json
import pathlib
import sys


def norm(s):
    return " ".join(s.split()).lower()


def load(d):
    p = pathlib.Path(d)
    return p, (p / "brief.md"), (p / "report.json")


def claims(d):
    """The ANCHORED claims of a round — the same set STALL compares against this round.
    Anchoring must be applied to both sides: an unanchored claim was discarded unread, so
    counting it here would dilute the overlap and hide a stall in the one case the loop
    exists for — a challenger that invents claims."""
    _, bp, rp = load(d)
    if not rp.exists():
        return set()
    try:
        r = json.loads(rp.read_text())
        hay = norm(bp.read_bytes().decode("utf-8", "replace"))
    except (json.JSONDecodeError, OSError):
        return set()
    return {norm(f["claim"]) for f in r.get("blocking_findings", []) if norm(f["claim"]) in hay}


def main():
    d = sys.argv[1]
    prev = sys.argv[2] if len(sys.argv) > 2 else None
    _, bp, rp = load(d)

    if not rp.exists() or not rp.stat().st_size:
        print("LEDGER verdict=NO_VERDICT reason=no-report")
        return 2

    brief = bp.read_bytes()
    sha = hashlib.sha256(brief).hexdigest()
    hay = norm(brief.decode("utf-8", "replace"))
    report = json.loads(rp.read_text())

    kept, dropped = [], []
    for f in report.get("blocking_findings", []):
        (kept if norm(f["claim"]) in hay else dropped).append(f)

    stalled = False
    if prev:
        now, before = {norm(f["claim"]) for f in kept}, claims(prev)
        if now and before:
            j = len(now & before) / len(now | before)
            stalled = j >= 0.82

    print(
        f"LEDGER brief_sha256={sha[:16]} model_verdict={report.get('verdict')} "
        f"blocking_kept={len(kept)} blocking_discarded={len(dropped)} "
        f"advisory={len(report.get('advisory_findings', []))} "
        f"unchallenged={len(report.get('unchallenged', []))} "
        f"research={len(report.get('independent_research', []))} "
        f"stalled={'yes' if stalled else 'no'}"
    )

    for f in dropped:
        print(f"  DISCARDED (unanchored) [{f['severity']}] {f['claim'][:80]!r}")
    for f in kept:
        print(f"\n  [{f['severity']}] claim: {f['claim']}")
        print(f"        defect: {f['defect']}")
        print(f"        fix:    {f['fix']}")

    if not kept and not report.get("unchallenged"):
        print("\n  WARNING: clean pass with an empty unchallenged[] — no declared coverage "
              "boundary. Absence of anchored findings is not evidence of absence.")
    if stalled:
        print("\n  STALL: this round repeats the previous round's claims. Stop the loop and "
              "surface both positions; do not spend another round.")
        return 3
    return 1 if kept else 0


if __name__ == "__main__":
    sys.exit(main())
