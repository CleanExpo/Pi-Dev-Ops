#!/usr/bin/env python3
"""
check_frozen_paths.py — fail a change that touches a frozen path.

The frozen list is .github/frozen-paths.txt (Mission Control consolidation,
founder-ratified 22/10/2026). A path is frozen if a pattern in the manifest at
the base commit OR the head commit matches it, so editing the manifest cannot
unfreeze a path in the same change that edits that path.

Usage:
  python3 scripts/check_frozen_paths.py --base <sha> --head <sha>
  python3 scripts/check_frozen_paths.py --verify-manifest [--min-files N]

Exit codes:
  0 — no frozen path changed (or, with --verify-manifest, the manifest is sound)
  1 — a frozen path changed, or the manifest has a dead/empty entry
  2 — script error (git failed, bad arguments)
"""

import argparse
import fnmatch
import subprocess
import sys

MANIFEST = ".github/frozen-paths.txt"


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def parse_manifest(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def manifest_at(rev):
    """Patterns from the manifest at `rev`, or None if the file does not exist there."""
    r = subprocess.run(["git", "show", "%s:%s" % (rev, MANIFEST)], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return parse_manifest(r.stdout)


def matches(pattern, path):
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    # `*` must not cross a directory boundary
    if pattern.count("/") != path.count("/"):
        return False
    return fnmatch.fnmatchcase(path, pattern)


def frozen_hits(patterns, paths):
    return sorted({p for p in paths for pat in patterns if matches(pat, p)})


def changed_paths(base, head):
    """Every path a change touches: both sides of renames and copies, and deletions."""
    out = git("diff", "--name-status", "-M", "%s...%s" % (base, head))
    paths = set()
    for line in out.splitlines():
        parts = line.split("\t")
        paths.update(parts[1:])
    return paths


def check_change(base, head):
    base_pats, head_pats = manifest_at(base), manifest_at(head)
    if base_pats is None and head_pats is None:
        print("No %s at base or head: nothing is frozen." % MANIFEST)
        return 0
    patterns = sorted(set(base_pats or []) | set(head_pats or []))
    if not patterns:
        print("FAIL: %s exists but lists no patterns — a freeze that freezes nothing." % MANIFEST)
        return 1
    paths = changed_paths(base, head)
    hits = frozen_hits(patterns, paths)
    print("Checked %d changed path(s) against %d frozen pattern(s)." % (len(paths), len(patterns)))
    if hits:
        print("FAIL: this change touches %d frozen path(s):" % len(hits))
        for h in hits:
            print("  " + h)
        print("Unfreeze first with a PR that changes only %s (founder merges)." % MANIFEST)
        return 1
    print("PASS: no frozen path changed.")
    return 0


def verify_manifest(min_files):
    patterns = manifest_at("HEAD")
    if patterns is None:
        print("FAIL: %s is not committed at HEAD." % MANIFEST)
        return 1
    tracked = git("ls-files").splitlines()
    dead, frozen = [], set()
    for pat in patterns:
        hit = [p for p in tracked if matches(pat, p)]
        if not hit:
            dead.append(pat)
        frozen.update(hit)
    for pat in dead:
        print("FAIL: pattern matches no tracked file: " + pat)
    print("%d pattern(s) freeze %d tracked file(s)." % (len(patterns), len(frozen)))
    if not patterns:
        print("FAIL: manifest lists no patterns.")
        return 1
    if len(frozen) < min_files:
        print("FAIL: expected at least %d frozen files." % min_files)
        return 1
    return 1 if dead else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--verify-manifest", action="store_true")
    ap.add_argument("--min-files", type=int, default=1)
    a = ap.parse_args(argv)
    try:
        if a.verify_manifest:
            return verify_manifest(a.min_files)
        if not (a.base and a.head):
            ap.error("--base and --head are required unless --verify-manifest")
        return check_change(a.base, a.head)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
