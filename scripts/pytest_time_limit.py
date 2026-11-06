"""Time limit for the handoff gate's ``pytest tests/`` run.

The base comes from measurement, not a constant. After each clean full run the
gate records its wall seconds in ``~/.receipts/pi-dev-ops/pytest-last-clean-seconds``
(per machine, outside any worktree). The base is ``max(420, ceil(1.5 x recorded))``;
no record, an unreadable one or a non-integer means 420. Three guessed constants
(180, 420, then RA-8171's load scaling over 420) were each outgrown by the suite.

RA-8171 load scaling still applies on top: ``base x max(1, load1 / cpus)``. The
1500 s ceiling caps both, so a record can only raise the limit up to it and a
genuine hang still dies.

Deliberately reads no env override: the release receipt re-runs the gate with no
env, and nothing a caller sets may switch the limit off or stretch it past the
ceiling. Stdlib only and Python 3.9 compatible, because the gate may run before
the venv is found.

``pytest_time_limit.py`` prints one line: ``<limit_seconds> <reason>``.
``pytest_time_limit.py record <seconds>`` stores a clean run's wall time.
"""
from __future__ import annotations

import math
import os
import re
import sys
import tempfile
from pathlib import Path

BASE_S = 420
CEILING_S = 1500
HEADROOM = 1.5


def record_path() -> Path:
    return Path.home() / ".receipts" / "pi-dev-ops" / "pytest-last-clean-seconds"


def _parse_seconds(text: str) -> int | None:
    text = text.strip()
    if not re.fullmatch(r"[0-9]+", text):  # str.isdigit() admits "²", which int() rejects
        return None
    value = int(text)
    return value if value > 0 else None


def base_from_record(text: str | None, floor: int = BASE_S, ceiling: int = CEILING_S) -> int:
    """Base limit from a recorded clean-run time. Anything unusable means ``floor``."""
    seconds = _parse_seconds(text) if text is not None else None
    if seconds is None:
        return floor
    return min(ceiling, max(floor, math.ceil(HEADROOM * seconds)))


def time_limit(load1: float, cpus: int, base: int = BASE_S, ceiling: int = CEILING_S) -> int:
    """Return the alarm in seconds. Unreadable or nonsense load means ``base``."""
    if not math.isfinite(load1) or load1 < 0:
        load1 = 0.0
    factor = max(1.0, load1 / max(1, cpus))
    return min(ceiling, math.ceil(base * factor))


def read_record(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write_record(path: Path, seconds: int) -> None:
    """Atomically replace the record: temp file in the same directory, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".pytest-last-clean.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{seconds}\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _record_cli(arg: str) -> int:
    seconds = _parse_seconds(arg)
    if seconds is None:
        print(f"refusing to record non-positive-integer seconds: {arg!r}", file=sys.stderr)
        return 2
    write_record(record_path(), seconds)
    print(f"recorded {seconds}s clean pytest run to {record_path()}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "record":
        return _record_cli(argv[1])
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        load1 = float("nan")
    cpus = os.cpu_count() or 1
    raw = read_record(record_path())
    base = base_from_record(raw)
    recorded = _parse_seconds(raw) if raw is not None else None
    limit = time_limit(load1, cpus, base=base)
    print(
        f"{limit} load1={load1:.2f} cpus={cpus} base={base}s "
        f"recorded={recorded if recorded is not None else 'none'} ceiling={CEILING_S}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
