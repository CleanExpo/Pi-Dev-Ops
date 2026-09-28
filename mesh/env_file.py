"""One key from the protected Hermes env file, never executing it.

Split out of runner.py at the 300-line convention (RA-7802).
"""
from __future__ import annotations

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
