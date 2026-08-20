#!/usr/bin/env python3
"""Stable CLI entry point for the Unlazy plan/scheduler core."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarm.unlazy_scheduler import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
