#!/usr/bin/env python3
"""Score a bench seat's output against the seeded defects in fixture/.

The harness measures one thing: did the seat surface the defect that was planted
for it. It does not judge prose. Recall is machine-scored; precision is not, and
the report says so rather than implying a number it did not compute.

  score.py --self-test                       run the three controls, exit 1 on failure
  score.py run.md [run2.md ...]              score one arm, human-readable
  score.py --json run.md                     same, machine-readable
  score.py --compare armA.json armB.json     per-defect hit rate, arm A vs arm B

Exit codes: 0 scored / 1 a control failed / 2 cannot determine (also a failure).
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = HERE / "defects.json"


def load_defects():
    if not MANIFEST.exists():
        print(f"cannot determine: manifest missing at {MANIFEST}", file=sys.stderr)
        sys.exit(2)
    return json.loads(MANIFEST.read_text())["defects"]


def matches(text, defect):
    """A defect is hit when every must_include term appears and every any_of
    group contributes at least one term. Case-insensitive substring matching:
    a seat that phrases the mechanism differently should still score."""
    low = text.lower()
    for term in defect.get("must_include", []):
        if term.lower() not in low:
            return False
    for group in defect.get("any_of", []):
        if not any(term.lower() in low for term in group):
            return False
    return True


def score_one(text, defects):
    return {d["id"]: matches(text, d) for d in defects}


def near_miss(text, defect):
    """Why a defect did not match: which must_include terms and which any_of
    groups failed. A miss failing exactly one group is the shape of a scorer
    false negative — the seat found the defect and phrased it a way the
    signature does not list. Three of three signature bugs so far were this."""
    low = text.lower()
    missing_terms = [t for t in defect.get("must_include", []) if t.lower() not in low]
    failed_groups = [i for i, g in enumerate(defect.get("any_of", []))
                     if not any(t.lower() in low for t in g)]
    return missing_terms, failed_groups


def audit_misses(runs, defects, owner_only=True):
    """Flag every miss that is one group away from a hit, for human review."""
    suspects = []
    for name, text in runs:
        for d in defects:
            if owner_only and d["expected_seat"] not in name:
                continue
            if matches(text, d):
                continue
            missing, failed = near_miss(text, d)
            if not missing and len(failed) == 1:
                idx = failed[0]
                suspects.append((name, d["id"], idx, d["any_of"][idx]))
    return suspects


# ---------------------------------------------------------------- controls

PERFECT = """
lib/sync-queue.ts writes nextAttemptAt in incrementRetry and drainQueue never reads it,
so the backoff is not enforced. getSyncStatus returns SYNCED while failed entries exist,
because failed is counted by neither branch and is therefore never surfaced to the user.
lib/notify.ts sendEmail is void and swallows every error, yet runWatchdog sets alerted
unconditionally, so the record is always true. In 002_policies.sql the "Anon read access"
policy is USING (true) and anon holds a GRANT, so every row of reports is readable.
lib/schema.prisma cascades from User through Inspection to AuditLog, so deleting a user
destroys the audit trail. 003_rls_fix.sql is committed but absent from the ledger and was
never applied. vitest.config.ts include globs do not match __tests__/engine.test.ts, so it
never runs. app/api/health/route.ts falls back to a hardcoded version, so the endpoint
cannot identify the running build.
"""

EMPTY = "PASS. Nothing to report.\n"

# Names every file and no mechanism. If this scores above zero the scorer is
# matching filenames rather than findings, and every number it prints is noise.
DECOY = """
I read lib/sync-queue.ts, lib/notify.ts, lib/schema.prisma, lib/engine.ts,
app/api/health/route.ts, vitest.config.ts, supabase/migrations/001_init.sql,
supabase/migrations/002_policies.sql, supabase/migrations/003_rls_fix.sql,
supabase/APPLIED_LEDGER.txt and __tests__/engine.test.ts.

The structure is conventional and the naming is consistent. The queue module is
cohesive, the schema is normalised, and the migrations are numbered in order.
I have no concerns about any of it.
"""


def self_test(defects):
    ids = [d["id"] for d in defects]
    failures = []

    perfect = score_one(PERFECT, defects)
    missed = [i for i in ids if not perfect[i]]
    if missed:
        failures.append(f"PERFECT control failed to score {missed} — signature too strict")

    empty = score_one(EMPTY, defects)
    fired = [i for i in ids if empty[i]]
    if fired:
        failures.append(f"EMPTY control scored {fired} — signature fires on nothing")

    decoy = score_one(DECOY, defects)
    fired = [i for i in ids if decoy[i]]
    if fired:
        failures.append(f"DECOY control scored {fired} — matching filenames, not findings")

    print(f"controls: {len(ids)} defects")
    print(f"  perfect artifact  {sum(perfect.values())}/{len(ids)}  (must be {len(ids)}/{len(ids)})")
    print(f"  empty artifact    {sum(empty.values())}/{len(ids)}  (must be 0/{len(ids)})")
    print(f"  decoy artifact    {sum(decoy.values())}/{len(ids)}  (must be 0/{len(ids)})")
    for f in failures:
        print(f"  FAIL {f}")
    if failures:
        return 1
    print("\nall three controls pass: the scorer can register a hit and can register a miss.")
    return 0


# ---------------------------------------------------------------- reporting

def read_text(paths):
    out = []
    for p in paths:
        f = pathlib.Path(p)
        if not f.exists():
            print(f"cannot determine: {p} does not exist", file=sys.stderr)
            sys.exit(2)
        out.append((p, f.read_text()))
    return out


def report(runs, defects, as_json):
    by_defect = {d["id"]: [] for d in defects}
    per_run = []
    for name, text in runs:
        s = score_one(text, defects)
        per_run.append({"run": name, "hits": s})
        for k, v in s.items():
            by_defect[k].append(v)

    rates = {k: (sum(v) / len(v) if v else 0.0) for k, v in by_defect.items()}

    if as_json:
        print(json.dumps({"runs": per_run, "hit_rate": rates}, indent=2))
        return 0

    n = len(runs)
    print(f"{n} run(s), {len(defects)} seeded defects\n")
    for d in defects:
        hits = sum(by_defect[d["id"]])
        mark = "HIT " if hits == n else ("MISS" if hits == 0 else "PART")
        print(f"  {mark}  {d['id']}  {hits}/{n}  {d['expected_seat']:<18} {d['title']}")
    total = sum(rates.values())
    print(f"\nrecall {total:.2f}/{len(defects)} defects on average per run")
    print("precision is NOT machine-scored — count off-target claims by hand before "
          "reading recall as quality.")
    return 0


def compare(a_path, b_path, defects):
    try:
        a = json.loads(pathlib.Path(a_path).read_text())["hit_rate"]
        b = json.loads(pathlib.Path(b_path).read_text())["hit_rate"]
    except Exception as e:
        print(f"cannot determine: {e}", file=sys.stderr)
        sys.exit(2)
    print(f"{'defect':<6} {'A':>6} {'B':>6}  delta")
    for d in defects:
        i = d["id"]
        x, y = a.get(i, 0.0), b.get(i, 0.0)
        print(f"{i:<6} {x:>6.2f} {y:>6.2f}  {y - x:+.2f}  {d['title']}")
    sa, sb = sum(a.values()), sum(b.values())
    print(f"\ntotal  {sa:>6.2f} {sb:>6.2f}  {sb - sa:+.2f}")
    print("\nA delta is only evidence if the two arms differed in exactly one variable.")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("artifacts", nargs="*")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = p.parse_args()

    defects = load_defects()

    if args.self_test:
        sys.exit(self_test(defects))
    if args.compare:
        sys.exit(compare(args.compare[0], args.compare[1], defects))
    if not args.artifacts:
        p.print_help()
        sys.exit(2)
    sys.exit(report(read_text(args.artifacts), defects, args.json))


if __name__ == "__main__":
    main()
