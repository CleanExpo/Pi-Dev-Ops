"""CLI for Levels 9 and 10: `scout`, `pick-first`, `ask-jev` (PLAN-scale.md rev 5). Shadow/advisory only.

Each takes `--repo` (an absolute path; default: the current directory's repository). The Jev key is
read from TYPESAFE_API_KEY at call time and never logged.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from jev_platform import ask, client, scout


def repo_root(path: str | None) -> str | None:
    """The repository top level, resolved by git under the fixed minimal environment."""
    if path is not None and not os.path.isabs(path):
        print("REFUSED: --repo must be an absolute path", file=sys.stderr)
        return None
    cmd = ["git", *(["-C", path] if path else []), "rev-parse", "--show-toplevel"]
    top = subprocess.run(cmd, capture_output=True, text=True, env=ask.git_env()).stdout.strip()
    if not top:
        print("REFUSED: not inside a git repository", file=sys.stderr)
    return top or None


def _jev_ready() -> bool:
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("BLOCKED: TYPESAFE_API_KEY not in environment (use `vercel env run`)", file=sys.stderr)
        return False
    return True


def _run(a, fn) -> int:
    if not _jev_ready():
        return 2
    repo = repo_root(a.repo)
    if repo is None:
        return 2
    out = fn(repo, a.post, client.Budget(a.max_usd, a.max_seconds))
    print(json.dumps(out, indent=1))
    return 2 if "blocked" in out or out.get("outcome") == "refused" else 0


def cmd_scout(a) -> int:
    return _run(a, lambda repo, post, budget: scout.scout_files(repo, a.glob, a.q, post, budget, a.prompt_id))


def cmd_pick_first(a) -> int:
    return _run(a, lambda repo, post, budget: scout.pick_first(repo, a.prompt_id, a.q, a.file, post, budget, a.floor))


def cmd_ask_jev(a) -> int:
    return _run(a, lambda repo, post, budget: scout.ask_jev(repo, a.prompt_id, a.file, a.q, post, budget))


def _common(p: argparse.ArgumentParser, max_usd: float) -> None:
    p.add_argument("--repo", help="absolute repository path (default: the current directory's repo)")
    p.add_argument("--max-usd", type=float, default=max_usd)
    p.add_argument("--max-seconds", type=float, default=900)


def register(sub, post) -> None:
    """Add the Level 9/10 subcommands; `post` is the live Jev transport from __main__."""
    s = sub.add_parser("scout", help="Level 9 ask_jev_files: approved templates over approved files by glob")
    s.add_argument("--glob", action="append", required=True, help="matched against manifest paths, never the disk")
    s.add_argument("--q", action="append", required=True, help="template id")
    s.add_argument("--prompt", "--prompt-id", dest="prompt_id", help="approved prompt id (adds `task` to state)")
    _common(s, 0.75)
    s.set_defaults(func=cmd_scout, post=post)
    f = sub.add_parser("pick-first", help="Level 9 pick_first_file over approved paths")
    f.add_argument("--prompt", "--prompt-id", dest="prompt_id", required=True)
    f.add_argument("--q", required=True, help="pick template id")
    f.add_argument("--file", action="append", required=True)
    f.add_argument("--floor", type=float, default=0.3)
    _common(f, 0.01)
    f.set_defaults(func=cmd_pick_first, post=post)
    j = sub.add_parser("ask-jev", help="Level 10: one Jev call over a bundle of approved files")
    j.add_argument("--prompt", "--prompt-id", dest="prompt_id", required=True)
    j.add_argument("--file", action="append", required=True)
    j.add_argument("--q", action="append", required=True)
    _common(j, 0.01)
    j.set_defaults(func=cmd_ask_jev, post=post)
