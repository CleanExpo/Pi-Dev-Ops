#!/usr/bin/env python3
"""scripts/run_codebase_wiki.py — RA-1968 CLI entry point for the codebase wiki updater.

Invoked by `.github/workflows/codebase-wiki.yml` after each merge to main.
Also runnable locally for ad-hoc refreshes.

Usage:
    python scripts/run_codebase_wiki.py --since=<sha> [--directories=a,b] [--dry-run] [--max-cost=0.02]

Exits 0 on success or graceful bypass; 1 on unhandled error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Update per-directory WIKI.md files.")
    p.add_argument("--repo-root", default=os.getcwd(), help="Repository root (default: cwd).")
    p.add_argument("--since", default=None, help="Commit SHA / ref to summarise from.")
    p.add_argument(
        "--directories",
        default=None,
        help="Comma-separated top-level directories to restrict the run to.",
    )
    p.add_argument("--dry-run", action="store_true", help="Skip SDK calls and file writes.")
    p.add_argument("--max-cost", type=float, default=0.02, help="Per-directory USD budget.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        from app.server.tao_codebase_wiki import update_wiki  # noqa: PLC0415
    except ImportError as exc:
        print(f"failed to import tao_codebase_wiki: {exc}", file=sys.stderr)
        return 1
    dirs = (
        [d.strip() for d in args.directories.split(",") if d.strip()]
        if args.directories
        else None
    )
    try:
        result = update_wiki(
            repo_root=args.repo_root,
            since_ref=args.since,
            max_cost_usd=args.max_cost,
            dry_run=args.dry_run,
            directories=dirs,
        )
    except Exception as exc:  # noqa: BLE001 — single-shot CLI; surface failures as exit 1
        print(f"update_wiki raised: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
