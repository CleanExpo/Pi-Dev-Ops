#!/usr/bin/env python3
"""Weekly false-green count: the before/after measure for Proof Loop Stage 1.

Spec: 2nd Brain Wiki/ops/false-positive-controls-2026-10-26/spec.md §9.0. Stage 2 (registry,
drills, grade) is built only if this count shows false greens Stage 1 did not stop.

A false green is a claim or check that read as passed/done/green while the work was wrong.
Two sources, each counted per ISO week and reported separately (never summed into one
number that hides which source moved):

  memory   memory files whose name or description records a false pass (fail-open, a check
           that could not fail, a stale or vacuous PASS). Counted by file birth time, so an
           edit to an old file does not move it into this week.
  reverts  merged PRs whose title starts "Revert" in the focus repos (gh; needs auth).

This is a heuristic instrument and says so: it misses false greens nobody wrote down, and a
keyword can match a memory about a false NEGATIVE. Its value is the trend on the same
instrument before and after, not the absolute number. A source that could not be read is
reported as UNKNOWN, never 0.

Usage: false_green_count.py [--weeks 6] [--json]
"""
import argparse
import datetime
import json
import os
import re
import subprocess

MEMORY = os.environ.get("FALSE_GREEN_MEMORY",
                        os.path.expanduser("~/.claude/projects/-Users-phill-mac/memory"))
REPOS = os.environ.get("FALSE_GREEN_REPOS",
                       "CleanExpo/Unite-Group,CleanExpo/Synthex,CleanExpo/skills-library").split(",")
PATTERN = re.compile(r"false[ _-]?(green|pass|positive)|fail[s]?[ _-]?open|cannot[ _-]fail|"
                     r"vacuous|exits?[ _-]?0|stale (receipt|pass)|declared[ _-]not[ _-]enforce",
                     re.IGNORECASE)


def week(ts):
    y, w, _ = datetime.date.fromtimestamp(ts).isocalendar()
    return "%d-W%02d" % (y, w)


def memory_counts():
    if not os.path.isdir(MEMORY):
        return None
    out = {}
    for name in os.listdir(MEMORY):
        if not name.endswith(".md") or name == "MEMORY.md":
            continue
        path = os.path.join(MEMORY, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                head = f.read(1500)
            st = os.stat(path)
        except OSError:
            continue
        if PATTERN.search(name) or PATTERN.search(head):
            born = getattr(st, "st_birthtime", st.st_mtime)
            out[week(born)] = out.get(week(born), 0) + 1
    return out


def revert_counts(since):
    out = {}
    for repo in REPOS:
        # `gh pr list --search` answers [] with exit 0 for a repo that does not exist or is not
        # visible (observed 26/10/2026), so an empty list proves nothing until the repo is read.
        try:
            seen = subprocess.run(["gh", "repo", "view", repo, "--json", "name"],
                                  capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if seen.returncode != 0:
            return None
        try:
            r = subprocess.run(["gh", "pr", "list", "--repo", repo, "--state", "merged",
                                "--search", "Revert in:title merged:>=%s" % since,
                                "--json", "title,mergedAt", "--limit", "200"],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode != 0:
            return None
        try:
            prs = json.loads(r.stdout or "[]")
        except ValueError:
            return None   # unreadable output is UNKNOWN, never zero reverts
        if not isinstance(prs, list) or len(prs) >= 200:
            return None   # a full page may hide more: the count would be a silent undercount
        for pr in prs:
            if not isinstance(pr, dict) or not isinstance(pr.get("mergedAt"), str):
                return None
            if not pr.get("title", "").startswith("Revert"):
                continue
            ts = datetime.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")).timestamp()
            out[week(ts)] = out.get(week(ts), 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    today = datetime.date.today()
    since = today - datetime.timedelta(weeks=a.weeks)
    weeks = []
    d = since
    while d <= today:
        w = week(datetime.datetime.combine(d, datetime.time()).timestamp())
        if w not in weeks:
            weeks.append(w)
        d += datetime.timedelta(days=1)
    mem, rev = memory_counts(), revert_counts(since.isoformat())
    rows = [{"week": w,
             "memory": "UNKNOWN" if mem is None else mem.get(w, 0),
             "reverts": "UNKNOWN" if rev is None else rev.get(w, 0)} for w in weeks]
    if a.json:
        print(json.dumps({"generated": today.isoformat(), "rows": rows}, indent=1))
    else:
        print("week      memory  reverts")
        for r in rows:
            print("%-9s %6s %8s" % (r["week"], r["memory"], r["reverts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
