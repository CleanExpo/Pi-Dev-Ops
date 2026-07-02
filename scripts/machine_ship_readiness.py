#!/usr/bin/env python3
"""Print machine-ship readiness JSON (no secrets). RA-6885."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.server.machine_ship_readiness import machine_ship_readiness


def main() -> int:
    report = machine_ship_readiness()
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
