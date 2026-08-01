#!/usr/bin/env python3
"""fail_open_check.py — find verification steps whose failure mode is silence.

A check that cannot fail is not a check. Five instances of this shipped in a
single day, each one looking green:

  1. loop fell through to GREEN when `gh api` errored     (ideas-drain loop)
  2. `it.skipIf(!baselineAvailable)` — suite passed unverified
  3. `continue` on an unresolved provenance pair — file never compared
  4. console.warn with no assertion — warned, then passed
  5. `.harness/*.jsonl` gitignore swallowed incidents.jsonl — the AUDIT TRAIL
     was untracked and would have died with the machine

(5) is the one that matters most: the evidence of the other four was itself
unrecorded. So this checker covers two distinct classes.

  CLASS A — code that swallows a failure signal
  CLASS B — evidence that is not durably recorded

Exit 0 clean · 1 findings · 2 could not run.
Read-only. Reports; never edits.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\Pi-Dev-Ops")

# Paths whose whole job is verification. A fail-open here is worth more than
# a fail-open in ordinary application code.
VERIFY_GLOBS = [
    "dashboard/__tests__/**/*.ts", "dashboard/__tests__/**/*.tsx",
    ".harness/loops/*.sh", "fence/*.py", "scripts/verify*", "scripts/check*",
]

# CLASS A — swallowed signals.
PATTERNS = [
    (r"\.skipIf\(|\bit\.skip\b|\bdescribe\.skip\b|\btest\.skip\b",
     "test skipped conditionally — a skipped check reports success having run nothing"),
    (r"catch\s*(\([^)]*\))?\s*\{\s*\}",
     "empty catch — the error is discarded and execution continues"),
    (r"except\s*(Exception)?\s*:\s*(pass|return\s+(True|None|0)\b)",
     "bare except swallowing the failure path"),
    (r"\|\|\s*(true|echo\s+0|:)\b",
     "shell fallback masks a non-zero exit"),
    (r"2>/dev/null(?!.*\|\|)",
     "stderr discarded without checking the exit code"),
    (r"console\.(warn|log)\([^)]*(?:UNAVAILABLE|SKIP|not verified|could not)",
     "warns about being unverified but does not fail"),
    (r"^\s*(continue|return)\s*;?\s*(#|//).*(skip|missing|absent|not found)",
     "loop skips an item that could not be checked, without recording it"),
]

# CLASS B — evidence that must be durably recorded, not just written to disk.
EVIDENCE = [
    ".harness/incidents.jsonl",
    ".harness/known-issues.md",
    ".harness/loops/ideas-drain-push-to-main.sh",
    "dashboard/__tests__/command-centre-provenance.json",
]


def sh(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout.strip()
    except Exception as exc:
        return 2, str(exc)


def class_a() -> list[str]:
    out, files = [], []
    for g in VERIFY_GLOBS:
        files.extend(REPO.glob(g))
    for f in sorted(set(files)):
        if not f.is_file() or f.name == "fail_open_check.py":
            continue          # scanning self always matches the pattern table
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = src.splitlines()
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith(("#", "//", "*")):
                continue                      # a comment describing the pattern is not the pattern
            # A justification normally sits ABOVE the line it excuses, so look back
            # a few lines as well as at the line itself.
            window = chr(10).join(lines[max(0, n - 5):n])
            if re.search(r"fail-open-ok:\s*\S", window):
                continue      # exempted with a stated reason - a visible decision
            for rx, why in PATTERNS:
                if re.search(rx, line, re.M):
                    out.append(f"A {f.relative_to(REPO)}:{n} — {why}\n    {line.strip()[:100]}")
                    break
    return out


def class_b() -> tuple[list[str], str | None]:
    """Declared evidence must be durably recorded, not just present on disk.

    SCOPE, stated because every sibling check that sources its list FROM git silently
    loses gitignored paths (see ".gitignore is a silent scope reducer" in
    .harness/lesson-patterns.md):

    This check does NOT have that defect, and the difference is deliberate. It does not
    enumerate through git. It walks a declared EVIDENCE list and asks git about each entry
    via `git ls-files --error-unmatch`. A gitignored evidence file makes that call FAIL, so
    it is reported loudly as "EXISTS BUT IS NOT TRACKED" instead of being dropped from the
    scope in silence. That is the fix pattern for the whole class: enumerate from an
    independent source, then ask git about each item.

    Its real limit is different and should not be conflated with the ignore problem: it can
    only check evidence that someone remembered to add to EVIDENCE. Undeclared evidence is
    invisible to it.
    """
    code, _ = sh(["git", "rev-parse", "--is-inside-work-tree"])
    if code != 0:
        return [], "not a git repo — CLASS B could not run"
    out = []
    for rel in EVIDENCE:
        p = REPO / rel
        if not p.exists():
            out.append(f"B {rel} — declared evidence does not exist on disk")
            continue
        code, _ = sh(["git", "ls-files", "--error-unmatch", rel])
        if code != 0:
            out.append(f"B {rel} — EXISTS BUT IS NOT TRACKED. Written to disk, "
                       f"invisible to the repo; dies with this machine.")
    return out, None


def main() -> int:
    a = class_a()
    b, err = class_b()

    print("FAIL-OPEN CHECK")
    print("=" * 62)
    print("\nCLASS A — verification code that swallows a failure signal")
    print("\n".join(f"  {x}" for x in a) if a else "  none")
    print("\nCLASS B — evidence that is not durably recorded")
    if err:
        print(f"  UNCHECKED: {err}")
    else:
        print("\n".join(f"  {x}" for x in b) if b else "  none")

    # Positive controls. A clean report from a broken scanner looks identical
    # to a clean report from a clean repo.
    ctl_a = bool(re.search(PATTERNS[1][0], "try { x() } catch {}"))
    ctl_b_code, _ = sh(["git", "ls-files", "--error-unmatch", "definitely-not-a-file-xyz"])
    ctl_b = ctl_b_code != 0
    print(f"\nPOSITIVE CONTROLS  classA-detects-planted={ctl_a}  classB-detects-untracked={ctl_b}")
    if not (ctl_a and ctl_b):
        print("  ** CONTROLS FAILED — this report proves nothing **")
        return 2

    total = len(a) + len(b)
    print(f"\nfindings: {total}   ({len(a)} class A, {len(b)} class B)")
    return 1 if total else (2 if err else 0)


if __name__ == "__main__":
    sys.exit(main())
