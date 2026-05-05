"""scripts/run_tao_context_mode.py — RA-1969 read-only CLI runner.

Build a CodebaseIndex, print stats + summaries, optionally expand specific
files. Intended for human inspection. Always exits 0.

Usage:
    python scripts/run_tao_context_mode.py --repo-root .
    python scripts/run_tao_context_mode.py --repo-root . --expand app/server/main.py
    python scripts/run_tao_context_mode.py --repo-root . --ignore tests,scripts
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("TAO_MAX_ITERS", "100000")

from app.server.tao_context_mode import (  # noqa: E402
    DEFAULT_IGNORE_GLOBS,
    build_index,
    expand,
    stats,
)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".", help="Repo root to index")
    p.add_argument("--ignore", default="", help="Comma-separated extra ignore globs")
    p.add_argument("--expand", action="append", default=[],
                   help="Path to expand (repeatable)")
    p.add_argument("--max-summaries", type=int, default=20,
                   help="Print at most this many summaries (default 20)")
    args = p.parse_args(argv[1:])

    extra = [g.strip() for g in args.ignore.split(",") if g.strip()]
    globs = list(DEFAULT_IGNORE_GLOBS) + extra
    repo_root = Path(args.repo_root).resolve()

    print(f"[run] indexing {repo_root}")
    index = build_index(repo_root, ignore_globs=globs)
    s = stats(index)
    print(f"[run] files_indexed={s['files_indexed']}, "
          f"bytes_indexed={s['bytes_indexed']}, "
          f"bypassed={s['bypassed']}")

    summaries = sorted(index.summaries.items())[: args.max_summaries]
    print(f"\n[run] first {len(summaries)} summaries:")
    for path, fs in summaries:
        sym = ", ".join(fs.symbols[:5])
        print(f"  - {path} ({fs.size_bytes}B, {fs.line_count}L) — {fs.summary} [{sym}]")

    for path in args.expand:
        if path in index.summaries:
            print(f"\n[run] === {path} (expanded) ===")
            print(expand(index, path))
        else:
            print(f"\n[run] WARNING: {path} not in index")

    if args.expand:
        s = stats(index)
        print(f"\n[run] post-expand stats: expansions={s['expansions']}, "
              f"expanded_bytes={s['expanded_bytes']}, hit_rate={s['hit_rate']}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
