"""What one mesh build run leaves behind: a transcript on disk and an outcome for the server (UNI-2796).

`run_claim` used to start `claude -p` with no output capture, so the agent's
stdout went wherever launchd pointed the runner's own stream, and the claim row
learned only `done` or `failed`. A failure's reason stayed on the machine that
had it. Warp's cloud-agent run list (see
`docs/RESEARCH-warp-adoption-gate-2026-09-28.md`) is the pattern: every run
keeps its log, exit code, duration and error.

Split out of runner.py for the same reason `fleet_state.py` was: runner.py sits
at the 300-line convention.

Redaction happens here, before anything leaves the machine, and again on the
server. This side uses the transcript bank in `scripts/sync_claude_sessions.py`
because it is the only bank that imports on a bare node python (the server's
`app.server.scanner` needs the server's dependencies and interpreter). If that
bank cannot load, `log_tail` is None rather than raw: a tail with no redaction
is exactly the leak this field must not become.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Optional

TAIL_CHARS = 4000
# The runner sends more than the server keeps. The server's bank knows secret
# shapes this one does not, and a shape this side cannot see is sliced by this
# side's cut. The server redacts the whole send, then keeps only the last
# TAIL_CHARS, so a server-only secret crossing this cut is dropped with the
# overlap unless it is longer than OVERLAP_CHARS.
OVERLAP_CHARS = 2000
SEND_CHARS = TAIL_CHARS + OVERLAP_CHARS
_READ_WINDOW = TAIL_CHARS * 4


def _load_bank() -> "Optional[list[re.Pattern[str]]]":
    """Compile the transcript secret bank, or None when it cannot be trusted."""
    try:
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.append(root)
        from scripts.sync_claude_sessions import _SECRET_PATTERNS  # noqa: PLC0415
        return [re.compile(p) for p, _tag in _SECRET_PATTERNS]
    except Exception:  # noqa: BLE001 — a missing bank must close the tail, not crash the run
        return None


_BANK = _load_bank()


def redacted_tail(text: str, bank: "Optional[list[re.Pattern[str]]]" = None) -> Optional[str]:
    """The last SEND_CHARS of `text`, with every bank match replaced; None without a bank.

    Redact first, cut second. Cutting first could slice a token at the cut, and a half token no longer matches the pattern that would catch it.
    """
    bank = _BANK if bank is None else bank
    if bank is None:
        return None
    for rx in bank:
        text = rx.sub("[REDACTED]", text)
    return text[-SEND_CHARS:]


class RunRecord:
    """One agent run: owns its log file, its process, and the fields it reports."""

    def __init__(self, run_id: str, base_dir: Path):
        """Open `<base_dir>/mesh-runs/<run_id>.log`, owner-readable only.

        A log that cannot be opened must not cost the run: the agent still runs
        with its output discarded, and the claim is still reported, with no tail.
        """
        self.run_id = run_id
        self.path: Optional[Path] = Path(base_dir) / "mesh-runs" / f"{run_id}.log"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._log: IO[bytes] = open(self.path, "wb")  # noqa: SIM115 — closed in close()
            self.path.chmod(0o600)
        except OSError:
            self.path, self._log = None, open(os.devnull, "wb")  # noqa: SIM115
        self.started = time.monotonic()
        self.proc: Optional[subprocess.Popen] = None

    def popen(self, cmd: list, cwd: str) -> subprocess.Popen:
        """Start the agent with stdout and stderr in this run's log."""
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=self._log, stderr=subprocess.STDOUT)
        return self.proc

    def close(self) -> None:
        """Close the log. Safe to call twice."""
        if not self._log.closed:
            self._log.close()

    def _tail(self) -> Optional[str]:
        """Read only the end of the log.

        The read window is well over the send. A token the window's start cuts
        in half therefore sits about 10k characters before the send and is
        discarded with it; the token that matters is the one crossing the send's
        cut, and the window holds it whole for `redacted_tail` to catch.
        """
        if self.path is None:
            return None
        try:
            with open(self.path, "rb") as fh:
                size = fh.seek(0, 2)
                fh.seek(max(0, size - _READ_WINDOW))
                text = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return None
        return redacted_tail(text)

    def fields(self, plan: dict) -> dict:
        """The run-record fields `/api/mesh/claim/update` stores next to the claim state."""
        self.close()
        return {
            "run_id": self.run_id,
            "duration_s": round(time.monotonic() - self.started, 1),
            "exit_code": getattr(self.proc, "returncode", None),
            "error": plan.get("error"),
            "log_tail": self._tail(),
        }
