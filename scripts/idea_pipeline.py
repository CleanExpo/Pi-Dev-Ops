#!/usr/bin/env python3
"""CLI for UNI-2633 — examine IDEAS.md, dispose with one word, record GO."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.server.idea_pipeline import (  # noqa: E402
    PipelineGateError,
    append_and_examine,
    authorize_go_for,
    daily_snapshot,
    dispose_idea,
    examine_intake,
    try_execute_idea,
)


def _print(payload: object) -> int:
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idea pipeline Board packet CLI")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("intake")
    add.add_argument("text")
    add.add_argument("--source", default="phill")
    sub.add_parser("examine")
    sub.add_parser("snapshot")
    disp = sub.add_parser("dispose")
    disp.add_argument("idea_id")
    disp.add_argument("verdict")
    go = sub.add_parser("go")
    go.add_argument("idea_id")
    exe = sub.add_parser("execute")
    exe.add_argument("idea_id")
    args = parser.parse_args(argv)
    root = args.root
    try:
        if args.cmd == "intake":
            return _print(append_and_examine(root, args.text, source=args.source))
        if args.cmd == "examine":
            return _print(examine_intake(root))
        if args.cmd == "snapshot":
            return _print(daily_snapshot(root))
        if args.cmd == "dispose":
            return _print(dispose_idea(root, args.idea_id, args.verdict))
        if args.cmd == "go":
            return _print(authorize_go_for(root, args.idea_id))
        return _print(try_execute_idea(root, args.idea_id))
    except (PipelineGateError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
