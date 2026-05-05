"""scripts/run_boomerang.py — RA-1994 CLI for tao_boomerang.

Usage:
    python scripts/run_boomerang.py "What is X?"
    python scripts/run_boomerang.py "q1" "q2" "q3" --max-parallel 3
    python scripts/run_boomerang.py --json "What is X?"

Exit codes: 0 all succeeded, 1 some failed/UNKNOWN.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.server.tao_boomerang import boomerang  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", nargs="+", help="One or more question strings")
    parser.add_argument("--timeout", type=int, default=120, help="Per-call timeout (s)")
    parser.add_argument("--max-parallel", type=int, default=5)
    parser.add_argument("--workspace", type=str, default=None)
    parser.add_argument("--json", action="store_true", help="Emit full batch as JSON")
    parser.add_argument("--session-id", type=str, default="cli-boomerang")
    args = parser.parse_args(argv)

    batch = asyncio.run(boomerang(
        questions=args.questions,
        workspace=args.workspace,
        timeout_s=args.timeout,
        max_parallel=args.max_parallel,
        session_id=args.session_id,
    ))

    if args.json:
        out = {
            "results": [asdict(r) for r in batch.results],
            "total_cost_usd": batch.total_cost_usd,
            "all_succeeded": batch.all_succeeded,
        }
        print(json.dumps(out, indent=2, default=str))
        return 0 if batch.all_succeeded else 1

    for r in batch.results:
        print(f"Q: {r.question}")
        if r.error:
            print(f"   ERROR: {r.error} ({r.elapsed_s}s)")
        elif r.is_unknown:
            print(f"   {r.summary} ({r.elapsed_s}s, ${r.cost_usd})")
        else:
            print(f"   {r.summary} ({r.elapsed_s}s, ${r.cost_usd})")
        print()
    print(f"Total cost: ${batch.total_cost_usd}")
    return 0 if batch.all_succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
