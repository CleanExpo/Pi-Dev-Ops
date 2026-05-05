"""scripts/run_session_search.py — RA-1991 CLI for pi_ceo_session_fts.

Usage:
    python scripts/run_session_search.py build
    python scripts/run_session_search.py rebuild
    python scripts/run_session_search.py search "RA-2002 ideas bridge" --limit 5
    python scripts/run_session_search.py search "margot" --since 2026-05-01
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a top-level script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.server import pi_ceo_session_fts as fts  # noqa: E402


def _cmd_build(_args: argparse.Namespace) -> int:
    stats = fts.build_index()
    print(json.dumps(stats.__dict__, indent=2, default=str))
    return 0 if stats.error is None else 1


def _cmd_rebuild(_args: argparse.Namespace) -> int:
    stats = fts.rebuild_incremental()
    print(json.dumps(stats.__dict__, indent=2, default=str))
    return 0 if stats.error is None else 1


def _cmd_search(args: argparse.Namespace) -> int:
    hits = fts.search(
        args.query, limit=args.limit, since=args.since, until=args.until,
    )
    if not hits:
        print(f"No hits for {args.query!r}")
        return 1
    for h in hits:
        print(f"[{h.score:6.2f}] {h.session_id} #{h.turn_index} ({h.role}) {h.ts_iso}")
        print(f"        {h.snippet}")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="Full rebuild of the FTS index.")
    sub.add_parser("rebuild", help="Incremental rebuild — only changed sessions.")
    p_search = sub.add_parser("search", help="BM25-ranked search.")
    p_search.add_argument("query", help="FTS5 query string.")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--since", default=None,
                          help="ISO-8601 lower bound on turn timestamp.")
    p_search.add_argument("--until", default=None,
                          help="ISO-8601 upper bound on turn timestamp.")
    args = parser.parse_args()
    return {
        "build": _cmd_build,
        "rebuild": _cmd_rebuild,
        "search": _cmd_search,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
