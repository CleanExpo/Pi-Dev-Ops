"""What one mesh build run leaves behind: a transcript on disk and an outcome for the server (UNI-2796).

`run_claim` used to start `claude -p` with no output capture, so the agent's
stdout went wherever launchd pointed the runner's own stream, and the claim row
learned only `done` or `failed`. A failure's reason stayed on the machine that
had it. Warp's cloud-agent run list (see
`docs/RESEARCH-warp-adoption-gate-2026-09-28.md`) is the pattern: every run
keeps its log, exit code, duration and error.

Split out of runner.py for the same reason `fleet_state.py` was: runner.py sits
at the 300-line convention.

**The transcript stays on this machine.** An earlier revision also sent a
redacted log tail. Three review rounds showed why it cannot be made safe here:
this side can only load the transcript bank in `scripts/sync_claude_sessions.py`
(the server's `app.server.scanner` needs the server's interpreter), so any
secret shape only the server knows reaches the cut unmatched, and every cut can
slice it past recognition. Sending a tail waits until a node can load the full
bank. Until then the server gets the outcome, and the log is on the node at
`~/.claude/mesh-runs/<run_id>.log`, owner-readable only.

`error` still crosses the wire, because it is how a failure's reason reaches the
fleet. It is short, runner-authored text, redacted here before sending and again
on the server. With no bank it is withheld rather than sent raw.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

ERROR_CHARS = 500


def _load_bank() -> "Optional[list[re.Pattern[str]]]":
    """Compile the transcript secret bank, or None when it cannot be trusted."""
    try:
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.append(root)
        from scripts.sync_claude_sessions import _SECRET_PATTERNS  # noqa: PLC0415
        return [re.compile(p) for p, _tag in _SECRET_PATTERNS] or None
    except Exception:  # noqa: BLE001 — a missing bank must withhold the error, not crash the run
        return None


_BANK = _load_bank()


def redact_error(text: Optional[str]) -> Optional[str]:
    """`text` with every bank match replaced, capped; None without a usable bank.

    An empty bank is no bank: it would match nothing and send the text raw.
    """
    if not text:
        return None
    if not _BANK:
        return None
    for rx in _BANK:
        text = rx.sub("[REDACTED]", text)
    return text[:ERROR_CHARS]


class RunRecord:
    """One agent run: owns its log file, its process, and the fields it reports.

    Construction never raises. A log that cannot be opened must not cost the
    run or strand the claim: the agent runs with its output discarded instead.
    """

    def __init__(self, run_id: str, base_dir: Path):
        """Open `<base_dir>/mesh-runs/<run_id>.log`, owner-readable only."""
        self.run_id = run_id
        self.path: Optional[Path] = Path(base_dir) / "mesh-runs" / f"{run_id}.log"
        self._log: Any = subprocess.DEVNULL
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.path, "wb")  # noqa: SIM115 — closed in close()
            self.path.chmod(0o600)
        except OSError:
            self.path = None
        self.started = time.monotonic()
        self.proc: Optional[subprocess.Popen] = None

    def popen(self, cmd: list, cwd: str) -> subprocess.Popen:
        """Start the agent with stdout and stderr in this run's log."""
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=self._log, stderr=subprocess.STDOUT)
        return self.proc

    def close(self) -> None:
        """Close the log. Safe to call twice, and on the DEVNULL fallback."""
        if hasattr(self._log, "close") and not self._log.closed:
            self._log.close()

    def fields(self, plan: dict) -> dict:
        """The run-record fields `/api/mesh/claim/update` stores next to the claim state."""
        self.close()
        return {
            "run_id": self.run_id,
            "duration_s": round(time.monotonic() - self.started, 1),
            "exit_code": getattr(self.proc, "returncode", None),
            "error": redact_error(plan.get("error")),
        }


def fields(rec: Optional[RunRecord], plan: dict) -> dict:
    """The fields to report for `rec`, or just the redacted error if it never existed."""
    if rec is None:
        return {"error": redact_error(plan.get("error"))}
    return rec.fields(plan)
