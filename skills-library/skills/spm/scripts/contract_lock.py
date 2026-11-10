#!/usr/bin/env python3
"""Lock /spm's normative text: any change to the rules must be a deliberate, reviewed event.

WHY. Four independent review rounds (18/10/2026) showed that no pattern match can prove what prose
means: each round found a new wording that kept every regex green while changing the rule (a
fenced table, a fraction, a reordered sentence, a self-contradicting clause). The structural tests
still document intent; this lock is the backstop. The SHA-256 of every normative file is recorded
in contract.lock. Changing a rule fails the suite until the lock is rewritten in the same commit,
and that rewrite is visible in the PR for the reviewer and the founder to approve.

    contract_lock.py --check     # exit 0 when every file matches the lock, 1 otherwise
    contract_lock.py --write     # re-record after an intended, reviewed change

Stdlib only.
"""
import hashlib
import json
import sys
from pathlib import Path

SPM = Path(__file__).resolve().parent.parent
LOCK = Path(__file__).resolve().parent / "contract.lock"
if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--root":
    SPM, LOCK = Path(sys.argv[2]), Path(sys.argv[2]) / "scripts" / "contract.lock"  # test seam
    sys.argv[1:] = ["--check"]


def normative() -> list:
    """The rule-bearing files: the skill text, its references, and the scripts whose constants
    ARE rules (thresholds, windows, tiers). Test files are not locked; they change with the rules."""
    scripts = SPM / "scripts"
    return [SPM / "SKILL.md", *sorted((SPM / "references").glob("*.md")),
            scripts / "tier.py", scripts / "contract_lock.py", scripts / "gitleaks.toml",
            scripts / "preflight.py", scripts / "journal_event.py"]


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def current() -> dict:
    return {str(p.relative_to(SPM)): digest(p) for p in normative()}


def check() -> list:
    if not LOCK.exists():
        return ["contract.lock is missing"]
    want = json.loads(LOCK.read_text())
    have = current()
    errs = [f"changed without re-locking: {f}" for f in sorted(have) if f in want and want[f] != have[f]]
    errs += [f"new normative file not in the lock: {f}" for f in sorted(set(have) - set(want))]
    errs += [f"locked file removed: {f}" for f in sorted(set(want) - set(have))]
    return errs


def main(argv) -> int:
    if argv == ["--write"]:
        LOCK.write_text(json.dumps(current(), indent=2, sort_keys=True) + "\n")
        print(f"locked {len(current())} normative /spm files")
        return 0
    if argv == ["--check"]:
        errs = check()
        for e in errs:
            print(f"FAIL {e}")
        print("PASS" if not errs else f"FAIL ({len(errs)}): a rule changed; review it, then run contract_lock.py --write in the same commit")
        return 0 if not errs else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
