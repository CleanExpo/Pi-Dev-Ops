#!/usr/bin/env python3
"""deploy_skills.py — materialise machine skills FROM the repo. One-way, never back.

RULING 2026-08-01: the repo is canonical; `~/.claude/skills/<name>/` is a deploy
artifact. Editing the machine copy in place is editing files on a production server,
and two-way sync is what produces diverging skills. Precedent already in the estate:
the Nexus Prompt is never forked into repos, always fetched live.

This is failure mode 4 — deployed-versus-template drift — which bit `proof-discipline`,
the file that catalogues it: it existed only on one machine, in a gitignored directory,
so the lesson inherited nowhere.

  deploy  : copy repo -> machine for every skill in MANIFEST
  --check : report drift without writing. Exit 1 if any copy differs. Used by CI.

Never reads the machine copy as a source. A local edit is drift to be reported and
overwritten, never merged.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MACHINE = Path.home() / ".claude" / "skills"

# Every skill whose source of truth is this repo. Adding one here makes the repo
# authoritative for it and puts it under drift enforcement.
MANIFEST = [
    # Split 2026-08-02 from one 480-line file, BY MOMENT rather than by size:
    #   control-design   loads while a check is being BUILT
    #   proof-discipline loads while something is being CLAIMED done
    # Both must be listed. A split half that is not in the manifest never deploys, which
    # would reproduce exactly the drift this manifest exists to prevent — and silently,
    # because the surviving half would still look healthy.
    "control-design",
    "proof-discipline",
    # the self-healing chain
    "prove-the-failure", "contain", "diagnose", "classify",
    "propose-fix", "adversarial-review", "verify", "immunise", "incident-memory",
]


def sha(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:
        return None


def main() -> int:
    check = "--check" in sys.argv
    drift, deployed, missing = [], [], []

    for name in MANIFEST:
        src = REPO / "skills" / name / "SKILL.md"
        dst = MACHINE / name / "SKILL.md"

        if not src.exists():
            missing.append(f"{name}: MISSING FROM REPO at {src}")
            continue

        s, d = sha(src), sha(dst)
        if s == d:
            continue

        if check:
            drift.append(
                f"{name}: machine {'absent' if d is None else d} != repo {s}"
                + ("" if d is None else "  <- a local edit, or a stale deploy")
            )
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            deployed.append(f"{name}: {d or 'absent'} -> {s}")

    print("SKILLS " + ("DRIFT CHECK" if check else "DEPLOY") + "  (repo -> machine, one-way)")
    print("=" * 62)
    print(f"  manifest: {len(MANIFEST)} skills")

    if missing:
        print("\n  MISSING FROM REPO — the repo is canonical, so this is a real gap:")
        for m in missing:
            print(f"    {m}")

    if check:
        print("\n  drift:" if drift else "\n  no drift — every machine copy matches the repo")
        for x in drift:
            print(f"    {x}")
    else:
        print("\n  deployed:" if deployed else "\n  nothing to deploy — already in sync")
        for x in deployed:
            print(f"    {x}")

    # Positive control: a clean report from a broken comparator is indistinguishable
    # from a clean repo, so prove the hash function discriminates before trusting it.
    ctl = sha(REPO / "skills" / MANIFEST[0] / "SKILL.md") != sha(Path(__file__))
    print(f"\n  POSITIVE CONTROL  hash-discriminates={ctl}")
    if not ctl:
        print("  ** CONTROL FAILED — this report proves nothing **")
        return 2

    return 1 if (drift or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
