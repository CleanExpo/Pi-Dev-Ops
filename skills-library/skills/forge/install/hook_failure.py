"""One line on disk every time a control dies, or declines to run.

THE PROBLEM THIS EXISTS FOR
---------------------------
Every hook in this tree is "default-safe": any unexpected error becomes a silent
`return 0`. That is the correct exit code — a broken hook must not wedge the
session — but it produces an artefact that is byte-identical to success. "Ran and
found nothing" and "died on line 89 and said nothing" are the same empty output,
the same exit 0, the same absent log file.

Measured on 2026-08-17: `03_quality_gate.py` had never written a single reviewer
verdict since it was authored. Two independent causes (a cp1252 UnicodeDecodeError
on the transcript, and `Popen(["/usr/bin/env", "python3", ...])` raising
FileNotFoundError on Windows) were both swallowed by `except Exception: return 0`.
The gate looked healthy for months because a dead control and a quiet one write
the same nothing.

A hook that cannot report its own failure is not a control. This module is how it
reports.

CONTRACT
--------
`record_failure` and `record_skip` MUST NOT raise, and MUST NOT block. They are
called from inside exception handlers; a logger that throws would convert a
swallowed error into a crashed hook. Every path is wrapped, and stderr is the
fallback channel when the file cannot be written — two channels, because one
silent logger reproduces the exact defect this file was written to end.

Stdlib only. No imports from anything else in this tree, so it cannot fail to
import because a sibling is broken.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

SWARM_DIR = Path.home() / "Pi-CEO" / ".harness" / "swarm"
FAILURE_LOG = SWARM_DIR / "hook-failures.jsonl"


def _append(record: dict) -> None:
    """Best effort, two channels, never raises."""
    line = ""
    try:
        line = json.dumps(record)
    except Exception:
        try:
            line = json.dumps({"kind": "FAILURE", "hook": str(record.get("hook")),
                               "where": "hook_failure._append", "error": "unserialisable record"})
        except Exception:
            return
    try:
        FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FAILURE_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return
    except Exception:
        pass
    # The file channel is gone. stderr is visible in Claude Code's hook output,
    # so a failure that cannot be logged is still not invisible.
    try:
        sys.stderr.write("[hook-failure] " + line + "\n")
    except Exception:
        pass


def _base(hook: str, where: str, kind: str) -> dict:
    return {
        "kind": kind,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hook": hook,
        "where": where,
        "pid": os.getpid(),
    }


def record_failure(hook: str, where: str, exc: BaseException | None = None,
                   note: str | None = None) -> None:
    """A control hit an error and is about to exit as if nothing happened."""
    rec = _base(hook, where, "FAILURE")
    if exc is not None:
        # str(exc) can itself raise. A reporter that dies inside an exception
        # handler converts a swallowed error into a crashed hook — the one thing
        # this module promises never to do.
        try:
            rec["error"] = f"{type(exc).__name__}: {exc}"
        except Exception:
            rec["error"] = f"{type(exc).__name__}: <unprintable>"
        try:
            rec["traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-1200:]
        except Exception:
            pass
    if note:
        rec["note"] = note
    _append(rec)


def record_skip(hook: str, reason: str) -> None:
    """A control declined to run. Skipped is not passed, so it leaves a mark.

    Distinct `kind` from FAILURE on purpose: a deliberate skip and a crash are
    different facts, and collapsing them would rebuild the ambiguity one level up.
    """
    rec = _base(hook, "skip", "SKIP")
    rec["reason"] = reason
    _append(rec)


# The child process spawned by 03_quality_gate.py runs via `python -c` and cannot
# import this module. It gets this snippet inlined instead, so the same failure
# channel covers the one place where verdicts were actually being lost.
CHILD_APPEND_SRC = '''
def _hook_fail(where, exc=None, note=None):
    """Inlined copy of hook_failure.record_failure for the -c child."""
    try:
        rec = {"kind": "FAILURE", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "hook": "03_quality_gate.reviewer-child", "where": where,
               "pid": __import__("os").getpid()}
        if exc is not None:
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        if note:
            rec["note"] = note
        p = Path(FAILURE_LOG)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\\n")
    except Exception:
        pass
'''
