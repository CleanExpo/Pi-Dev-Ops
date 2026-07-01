#!/usr/bin/env python3
"""CLI entry for machine spec pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.server.spec_pipeline import run_pipeline_sync


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run machine spec pipeline")
    parser.add_argument("--proposal", required=True, help="Proposal text to judge and build")
    parser.add_argument("--dry-run", action="store_true", help="Stop after boardroom (no build/ship)")
    parser.add_argument("--live", action="store_true", help="Require TAO_MACHINE_SHIP_MODE=1 for build")
    parser.add_argument("--json", action="store_true", help="Print result JSON")
    args = parser.parse_args(argv)

    dry_run = args.dry_run or not args.live
    result = run_pipeline_sync(
        proposal=args.proposal,
        trigger="cli",
        dry_run=dry_run,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"pipeline_id={result.pipeline_id} status={result.status} reason={result.reason}")
        if result.pr_url:
            print(f"pr_url={result.pr_url}")
    return 0 if result.status in ("complete", "dry_complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
