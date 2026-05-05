#!/usr/bin/env python3
"""scripts/run_tao_loop.py — RA-1970 CLI runner for the judge-gated TAO loop.

Usage:

    python scripts/run_tao_loop.py \
        --goal "implement X" \
        --workspace /path/to/repo \
        --max-iters 10 \
        --max-cost 1.50 \
        --judge-every 1

Exit codes:
    0 — reason == "GOAL_MET"
    1 — any other terminal reason (kill-switch, judge never satisfied, etc.)

Streams `on_event` payloads to stderr as JSONL. Final LoopResult to stdout as JSON.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from pathlib import Path

# Allow running from a checkout without `pip install -e .`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.server.tao_loop import run_until_done  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RA-1970 judge-gated TAO loop runner")
    p.add_argument("--goal", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--max-iters", type=int, default=None)
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--judge-every", type=int, default=1)
    p.add_argument("--timeout-per-iter", type=int, default=600)
    return p.parse_args()


def _emit_event(payload: dict) -> None:
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.stderr.flush()


def _result_to_dict(result) -> dict:  # type: ignore[no-untyped-def]
    d = dataclasses.asdict(result)
    # judge_history items are dataclass instances → already dict-ified.
    return d


async def _amain(args: argparse.Namespace) -> int:
    result = await run_until_done(
        goal=args.goal,
        workspace=args.workspace,
        max_iters=args.max_iters,
        max_cost_usd=args.max_cost,
        judge_every_n_iters=args.judge_every,
        timeout_per_iter_s=args.timeout_per_iter,
        on_event=_emit_event,
    )
    sys.stdout.write(json.dumps(_result_to_dict(result), default=str) + "\n")
    sys.stdout.flush()
    return 0 if result.reason == "GOAL_MET" else 1


def main() -> int:
    args = _parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
