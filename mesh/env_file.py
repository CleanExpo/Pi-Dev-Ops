"""Keys from the protected Hermes env file, never executing it; the fleet key resolver.

Split out of runner.py at the 300-line convention (RA-7802).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def from_env_file(name: str) -> str:
    """Read one key from the protected Hermes env file without executing it."""
    envf = Path.home() / ".hermes" / ".env"
    if not envf.exists():
        return ""
    try:
        for raw in envf.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return ""
    return ""


def resolve_key(name: str) -> str:
    """The provisioned key wins: ~/.hermes/.env first, then the process environment.

    The environment used to win. On Phill_Desktop a stale User-level
    PI_CEO_API_KEY (21 chars) silently overrode the provisioned one in
    .hermes/.env, so every heartbeat was refused with a 401 (RA-7905). When
    both are set and differ, say so on stderr — names only, never values.
    """
    disk = from_env_file(name)
    env = (os.environ.get(name) or "").strip()
    if disk and env and disk != env:
        sys.stderr.write(f"[mesh] {name}: the environment value differs from ~/.hermes/.env; "
                         "using ~/.hermes/.env (RA-7905)\n")
    return disk or env
