#!/usr/bin/env python3
"""symlink_precondition.py - container mount precondition (PROPOSAL §9.5.2 residual 2).

The reviewer container bind-mounts the repo read-only. Docker Desktop's 9p mount carries
`symlinkroot=/mnt/host/`, so a symlink inside the tree pointing outside it is a plausible
traversal route out of the mount. Testing that vector directly needs an elevated shell
(creating a symlink on Windows requires Administrator). This check does not replace that
test - it removes the *input* the vector needs, git-side, with no privileges.

Enumerates every tracked symlink (git mode 120000) and FAILS CLOSED if any target resolves
outside the tree, or cannot be resolved.

    python scripts/symlink_precondition.py [--rev HEAD] [--self-test]

Exit: 0 clean · 1 escaping symlink found · 2 could not run (fail closed).
"""
from __future__ import annotations
import argparse, subprocess, sys, posixpath

def git(*a: str) -> str:
    r = subprocess.run(["git", *a], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"  [ERROR] git {' '.join(a)}: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout

def escapes(link_path: str, target: str) -> tuple[bool, str]:
    """True if `target`, resolved relative to `link_path`'s dir, leaves the tree."""
    t = target.replace("\\", "/")
    if t.startswith("/") or (len(t) > 1 and t[1] == ":"):
        return True, f"absolute target {t!r}"
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(link_path), t))
    if resolved.startswith("../") or resolved == ".." or resolved.startswith("/"):
        return True, f"resolves to {resolved!r}"
    return False, resolved

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rev", default="HEAD")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        # RED FIRST. A check that has never rejected anything is a string in a file.
        cases = [("a/b/link", "../../../etc/passwd", True), ("a/b/link", "/etc/passwd", True),
                 ("a/b/link", "C:/Users/x/.ssh/id_ed25519", True), ("a/b/link", "../c/file", False),
                 ("a/b/link", "sibling", False)]
        bad = [(l, t, e, escapes(l, t)[0]) for l, t, e in cases if escapes(l, t)[0] != e]
        for l, t, e, got in bad:
            print(f"  SELF-TEST FAIL: {l} -> {t}  expected escape={e} got={got}")
        print(f"  self-test: {len(cases) - len(bad)}/{len(cases)} cases correct")
        return 1 if bad else 0

    links = []
    for line in git("ls-tree", "-r", args.rev).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if parts and parts[0] == "120000":
            links.append((path, parts[2]))

    print(f"  tracked symlinks at {args.rev}: {len(links)}")
    findings = []
    for path, sha in links:
        target = git("cat-file", "blob", sha).strip()
        bad, detail = escapes(path, target)
        print(f"    {'ESCAPES' if bad else 'ok     '}  {path} -> {target}  ({detail})")
        if bad:
            findings.append((path, target, detail))

    if findings:
        print(f"\n  ==== PRECONDITION FAILED - {len(findings)} symlink(s) point outside the tree.")
        print("       A read-only mount does not contain a symlink that resolves past its root.")
        return 1
    print("\n  ==== PRECONDITION HOLDS - no tracked symlink resolves outside the tree.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
