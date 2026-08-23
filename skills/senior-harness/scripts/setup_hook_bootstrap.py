#!/usr/bin/env python3
"""Fail-closed watchdog for lifecycle-hook interpreter and import failures."""
from __future__ import annotations

import runpy
import signal
import sys


TIMEOUT_SECONDS = 30


def _timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("Senior Harness hook exceeded its runtime limit")


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or sys.argv[1:])
    if not arguments:
        print("Senior Harness hook bootstrap has no driver path", file=sys.stderr)
        return 2
    driver, *driver_arguments = arguments
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(TIMEOUT_SECONDS)
    sys.argv = [driver, *driver_arguments]
    try:
        runpy.run_path(driver, run_name="__main__")
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else 1
        if status == 0:
            return 0
        print("Senior Harness hook driver failed closed", file=sys.stderr)
        return 2
    except BaseException as exc:
        print(
            f"Senior Harness hook failed closed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
