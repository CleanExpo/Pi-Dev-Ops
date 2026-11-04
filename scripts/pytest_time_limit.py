"""Time limit for the handoff gate's ``pytest tests/`` run, scaled by machine load.

RA-8171. A fixed 420 s alarm killed clean runs at ~89% on a 10-core machine at
load 11-14, because other agents were running their own suites. The limit now
grows with the run queue: ``420 x max(1, load1 / cpus)``, capped at 1500 s so a
genuine hang still dies.

Deliberately reads no env var: the release receipt re-runs the gate with no env,
and nothing a caller sets may switch the limit off or stretch it.
Stdlib only and Python 3.9 compatible, because the gate may run before the venv
is found.

Prints one line: ``<limit_seconds> <reason>``.
"""
from __future__ import annotations

import math
import os

BASE_S = 420
CEILING_S = 1500


def time_limit(load1: float, cpus: int, base: int = BASE_S, ceiling: int = CEILING_S) -> int:
    """Return the alarm in seconds. Unreadable or nonsense load means ``base``."""
    if not math.isfinite(load1) or load1 < 0:
        load1 = 0.0
    factor = max(1.0, load1 / max(1, cpus))
    return min(ceiling, math.ceil(base * factor))


def main() -> int:
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        load1 = float("nan")
    cpus = os.cpu_count() or 1
    limit = time_limit(load1, cpus)
    print(f"{limit} load1={load1:.2f} cpus={cpus} base={BASE_S}s ceiling={CEILING_S}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
