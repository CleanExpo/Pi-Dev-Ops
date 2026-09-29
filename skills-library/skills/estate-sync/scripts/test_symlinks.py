#!/usr/bin/env python3
"""Tracked symlinks in skills-library must never have an ABSOLUTE target.

WHY. This repo tracks ~135 symlinks into sibling repos. An absolute target
encodes one machine's home directory into a file that syncs to every machine —
so it resolves on exactly one box and dangles everywhere else, while git happily
propagates the breakage. The skill then silently does not exist: the router still
points at it, the Skill tool just fails.

That is the estate's recurring failure mode, fourth instance:
  FABLE_PLAYBOOK.md  lived unsynced in ~/.hermes      -> loaded on no machine
  hooks/ + settings  gitignored                       -> loop ran on the Mini only
  .github/           never allowlisted                -> no CI could exist
  absolute symlinks  /Users/phill-mac/... hardcoded   -> resolves on the Mini only

It is also self-inflicted and recent. fee2698 (2026-07-16) tried to fix two
absolute supabase links by repointing them to `../../.agents/skills/supabase`.
That is the wrong directory — the real target is `../../2nd Brain/.agents/...`,
which exists on BOTH machines. The "fix" made them resolve here and dangle on the
Mini: two fixed, two broken, net zero. Whack-a-mole is what happens without a gate.

WHAT THIS CANNOT CHECK. Whether a relative target actually resolves. CI has no
sibling repos checked out, so every link legitimately dangles on the runner.
Absoluteness is the only property decidable here; dangle-reporting belongs on a
real machine and already lives in bootstrap.sh. Do not "improve" this into a
resolution check — it would fail CI for a healthy repo.

Stdlib only, no pytest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def tracked_symlinks(repo: Path = REPO) -> dict[str, str]:
    """Map of path -> target for every symlink git tracks (mode 120000)."""
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-s"],
                         capture_output=True, text=True, timeout=60).stdout
    links = {}
    for line in out.splitlines():
        if not line.startswith("120000"):
            continue
        path = line.split("\t", 1)[1]
        target = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-p", f":{path}"],
            capture_output=True, text=True, timeout=60).stdout.strip()
        links[path] = target
    return links


def t0_the_reader_works_on_a_repo_that_has_one() -> None:
    """Positive control for tracked_symlinks(), replacing an assertion that is about to
    become a false alarm.

    t1 used to assert `links` was non-empty, on the reasoning that finding none meant the
    reader was broken. That held while the repo carried ~145 tracked symlinks. On
    31/08/2026, 132 were vendored into the repo as real files and 13 remain — and when
    those 13 are resolved too, a healthy repo will legitimately have zero, and t1 would
    fail with "the check is broken, not the repo" while the repo was perfect.

    So prove the reader works the only way that stays true at zero: build a throwaway repo
    with a symlink in it and require the reader to find it.
    """
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "real.txt").write_text("x")
        os.symlink("real.txt", repo / "link.txt")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                       capture_output=True)
        found = tracked_symlinks(repo)
    assert found == {"link.txt": "real.txt"}, (
        f"tracked_symlinks() could not see a symlink in a repo that provably has one — "
        f"the reader is broken, so t1's and t2's greens mean nothing. got={found}")


def t1_no_absolute_targets() -> None:
    """THE GATE. No tracked symlink may point at an absolute path."""
    links = tracked_symlinks()

    absolute = {p: t for p, t in links.items() if t.startswith("/")}
    if absolute:
        detail = "\n".join(f"    {p} -> {t}" for p, t in sorted(absolute.items()))
        raise AssertionError(
            f"{len(absolute)} tracked symlink(s) have an ABSOLUTE target. These encode one "
            f"machine's home into a synced file — they resolve on that box and dangle on every "
            f"other, and git propagates the breakage:\n{detail}\n"
            f"  Fix: make the target relative to the link's own directory (e.g. "
            f"'../../Pi-Dev-Ops/skills/foo'), or untrack it if the target is machine-local "
            f"and let bootstrap.sh create it where the target exists.")


def t2_no_other_machines_home() -> None:
    """Belt and braces: catch a known-foreign home even if made relative.

    A relative target that walks up into another machine's home (e.g.
    '../../../phill-mac/...') is absolute-by-other-means.
    """
    links = tracked_symlinks()
    foreign = {p: t for p, t in links.items() if "phill-mac" in t or "Users/" in t}
    assert not foreign, (
        f"tracked symlink(s) reference a specific user's home:\n"
        + "\n".join(f"    {p} -> {t}" for p, t in sorted(foreign.items())))


TESTS = (t0_the_reader_works_on_a_repo_that_has_one,
         t1_no_absolute_targets, t2_no_other_machines_home)


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
