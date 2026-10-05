#!/usr/bin/env python3
"""The two tracked copies of the evidence gate must not drift.

The repo tracks the gate and its reporter TWICE — once as installer source under
skills/forge/install/, once as the installed artefact under hooks/. Nothing checked
that they agreed, and they did not: measured 29/08/2026 on origin/main, the two copies
of 04_evidence_gate.py differed by 26 lines, the forge copy 20 lines older and missing
the hook_failure import and the UTF-8 decoding fixes entirely. Whichever copy a reader
opened, they learned something false about the other. A fork between two tracked copies
of an enforcement control is not a style issue — it is two different gates wearing one
name.

Separate from test_evidence_gate.py on purpose. That suite must stay RELOCATABLE so
positive_control.py can copy skills/forge/ elsewhere and sabotage it; this check is
inherently repo-rooted, and leaving it in the suite made every sabotage run go red for
the wrong reason. Splitting them keeps each provable.

Fails closed: an unlocatable repo root is an error, never a skip. A check that quietly
declines to run is the defect the gate it guards exists to catch.

Usage:  python3 skills/forge/tests/check_copies_in_step.py
Stdlib only, read-only, no network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PAIRS = [
    ("skills/forge/install/04_evidence_gate.py", "hooks/Stop/04_evidence_gate.py"),
    ("skills/forge/install/hook_failure.py", "hooks/hook_failure.py"),
]


def repo_root() -> Path:
    """Ask git, then fall back to walking up for .git. Never guess silently."""
    here = Path(__file__).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=here.parent, capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:  # noqa: BLE001 — git absent or unusable; fall through
        pass
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    print("ERROR: cannot locate the repository root, so the copies cannot be compared.\n"
          "       This check FAILS rather than skipping: a comparison that did not happen\n"
          "       must never read as a comparison that passed.", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    root = repo_root()
    failures = 0
    for a, b in PAIRS:
        pa, pb = root / a, root / b
        missing = [str(p) for p in (pa, pb) if not p.exists()]
        if missing:
            print(f"FAIL  {a}\n      missing tracked copy: {', '.join(missing)}")
            failures += 1
            continue
        if pa.read_bytes() != pb.read_bytes():
            print(f"FAIL  {a}\n      has drifted from {b}. They are the same control;\n"
                  f"      update both in the same commit, or stop tracking one of them.")
            failures += 1
        else:
            print(f"OK    {a} == {b}")
    total = len(PAIRS)
    print(f"\n{total - failures}/{total} tracked pairs in step")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
