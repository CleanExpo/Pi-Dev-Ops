#!/usr/bin/env python3
"""RA-6911 — list or delete stale Pi-Dev-Ops remote branches.

Safe-delete rules:
  * Branch has a MERGED PR (headRefName match), OR
  * Branch matches ``pidev/auto-*`` with no open PR

Never deletes: main, branches with open PRs, unclassified manual branches.

Usage:
  python scripts/prune_stale_branches.py              # dry-run list
  python scripts/prune_stale_branches.py --delete     # delete safe branches
"""
from __future__ import annotations

import argparse
import json
import subprocess


def gh_json(args: list[str]) -> list[dict]:
    out = subprocess.check_output(
        ["env", "-u", "GITHUB_TOKEN", "gh", *args],
        text=True,
    )
    return json.loads(out) if out.strip() else []


def list_branches() -> list[str]:
    out = subprocess.check_output(
        [
            "env", "-u", "GITHUB_TOKEN", "gh", "api",
            "repos/CleanExpo/Pi-Dev-Ops/branches",
            "--paginate", "-q", ".[].name",
        ],
        text=True,
    )
    return [b.strip() for b in out.strip().splitlines() if b.strip()]


def classify() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    merged = {p["headRefName"] for p in gh_json(
        ["pr", "list", "--state", "merged", "--limit", "500", "--json", "headRefName"],
    )}
    open_prs = {p["headRefName"] for p in gh_json(
        ["pr", "list", "--state", "open", "--limit", "100", "--json", "headRefName"],
    )}
    safe: list[tuple[str, str]] = []
    keep: list[tuple[str, str]] = []
    for branch in list_branches():
        if branch in {"main", "master"}:
            continue
        if branch in open_prs:
            keep.append((branch, "open-pr"))
        elif branch in merged:
            safe.append((branch, "merged-pr"))
        elif branch.startswith("pidev/auto-"):
            safe.append((branch, "pidev-zombie"))
        else:
            keep.append((branch, "manual-review"))
    return safe, keep


def delete_branch(name: str) -> bool:
    proc = subprocess.run(
        [
            "env", "-u", "GITHUB_TOKEN", "gh", "api", "-X", "DELETE",
            f"repos/CleanExpo/Pi-Dev-Ops/git/refs/heads/{name}",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune stale Pi-Dev-Ops branches (RA-6911)")
    parser.add_argument("--delete", action="store_true", help="Delete safe branches (default: dry-run)")
    args = parser.parse_args()

    safe, keep = classify()
    print(f"safe_to_delete={len(safe)} keep={len(keep)}")
    for branch, reason in safe:
        print(f"{'DELETE' if args.delete else 'WOULD_DELETE'}\t{reason}\t{branch}")

    if keep:
        print("--- keep ---")
        for branch, reason in keep:
            print(f"KEEP\t{reason}\t{branch}")

    if not args.delete:
        print("\nDry-run only. Re-run with --delete to remove safe branches.")
        return 0

    failed = 0
    for branch, _ in safe:
        ok = delete_branch(branch)
        print(f"{'ok' if ok else 'FAIL'}\t{branch}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
