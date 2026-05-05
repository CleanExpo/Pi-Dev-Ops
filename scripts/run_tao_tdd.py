"""scripts/run_tao_tdd.py — RA-1992 CLI wrapper for tao_tdd_pipeline.

Usage:
    python scripts/run_tao_tdd.py \\
        --goal "implement hex parser; tests cover empty / non-hex / 0x-prefix" \\
        --workspace /path/to/repo \\
        --max-iters 10 \\
        --max-cost 1.50 \\
        --judge-every 1

Exit codes:
    0 — done=True (loop GOAL_MET + tests green + test files in diff)
    1 — loop terminated but TDD discipline violated or tests still red
    2 — loop kill-switched / never met goal
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

from app.server.tao_tdd_pipeline import run_tdd  # noqa: E402


def _stderr_event(evt: dict) -> None:
    sys.stderr.write(f"[iter {evt.get('iters', '?')}] {json.dumps(evt)}\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="TDD goal description")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--max-iters", type=int, default=None)
    parser.add_argument("--max-cost", type=float, default=None,
                        help="Max cost in USD (else honour TAO_MAX_COST_USD)")
    parser.add_argument("--judge-every", type=int, default=1,
                        help="Judge call cadence (every N iters)")
    parser.add_argument("--timeout-per-iter", type=int, default=600)
    parser.add_argument("--session-id", default="cli-tdd")
    args = parser.parse_args(argv)

    if not args.workspace.is_dir():
        sys.stderr.write(f"[fatal] workspace not a directory: {args.workspace}\n")
        return 2

    result = asyncio.run(run_tdd(
        goal=args.goal,
        workspace=str(args.workspace),
        max_iters=args.max_iters,
        max_cost_usd=args.max_cost,
        timeout_per_iter_s=args.timeout_per_iter,
        on_event=_stderr_event,
        session_id=args.session_id,
        judge_every_n_iters=args.judge_every,
    ))

    out_payload = {
        "done": result.done,
        "reason": result.reason,
        "loop_done": result.loop.done,
        "loop_reason": result.loop.reason,
        "iters": result.loop.iters,
        "cost_usd": result.loop.cost_usd,
        "test_files_modified": result.test_files_modified,
        "final_pytest_passed": result.final_pytest_passed,
        "discipline_violations": result.discipline_violations,
        "judge_history": [asdict(v) for v in result.loop.judge_history],
    }
    print(json.dumps(out_payload, indent=2))

    if result.done:
        return 0
    if result.loop.done:
        # Loop said GOAL_MET but TDD discipline blocked it.
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
