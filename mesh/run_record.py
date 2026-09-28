"""What one mesh build run leaves behind: a transcript on disk and an outcome for the server (UNI-2796).

`run_claim` used to start `claude -p` with no output capture, so the agent's
stdout went wherever launchd pointed the runner's own stream, and the claim row
learned only `done` or `failed`. A failure's reason stayed on the machine that
had it. Warp's cloud-agent run list (see
`docs/RESEARCH-warp-adoption-gate-2026-09-28.md`) is the pattern: every run
keeps its log, exit code, duration and failure reason.

Split out of runner.py for the same reason `fleet_state.py` was: runner.py sits
at the 300-line convention.

**No free text leaves this machine.** Four review rounds found secrets crossing
the wire in every free-text field tried: first a redacted log tail, then a
redacted error string. The cause is structural — a node can only load the
transcript secret bank, the server knows more shapes, and text the node cannot
recognise goes out raw. So the node sends facts, not prose: run id, duration,
exit code, and an `error_code` from the closed set below. Not even an
exception's class name is sent: a class can be named anything. The full log and
the full error text stay here, at `~/.claude/mesh-runs/<run_id>.log` (0600).
Shipping a log tail safely is UNI-2800.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

# run_claim's ids are uuid4().hex[:8]. Anything else never becomes a path.
_RUN_ID = re.compile(r"[0-9a-f]{8,32}")
# Failure reasons the runner itself writes, by prefix -> the code that is sent.
_ERROR_CODES = (
    ("agent exited", "agent_exit"),
    ("timed out", "timeout"),
    ("repo missing", "repo_missing"),
    ("git worktree add failed", "worktree_add_failed"),
)


def error_code(plan: dict) -> Optional[str]:
    """The closed-set code for this plan's failure, or None when it did not fail.

    An exception is sent as `runner_exception_os` or `runner_exception`, never
    its message or its class name: both are free text somebody else chose.
    """
    if plan.get("error_code"):
        return plan["error_code"]
    text = plan.get("error")
    if not text:
        return None
    for prefix, code in _ERROR_CODES:
        if text.startswith(prefix):
            return code
    return "runner_exception"


def _open_private(path: Path) -> Any:
    """Open `path` for writing as owner-only from the first byte, or return DEVNULL.

    The mode is set at creation (`os.open`), not afterwards, so there is no
    window in which the log exists with the umask's wider mode; `fchmod` covers
    a file that somehow already existed. Any failure removes what was created.
    """
    fd = -1
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, "wb")
    except OSError:
        if fd >= 0:
            os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
        return subprocess.DEVNULL


class RunRecord:
    """One agent run: owns its log file, its process, and the fields it reports.

    Construction never raises. A log that cannot be opened safely must not cost
    the run or strand the claim: the agent runs with its output discarded instead.
    """

    def __init__(self, run_id: str, base_dir: Path):
        """Open `<base_dir>/mesh-runs/<run_id>.log`, owner-readable only.

        A run id that is not the generated hex id opens nothing: it could name a
        path outside mesh-runs, and os.open truncates what it opens.
        """
        self.run_id = run_id
        self.path: Optional[Path] = None
        self._log: Any = subprocess.DEVNULL
        if _RUN_ID.fullmatch(run_id):
            path = Path(base_dir) / "mesh-runs" / f"{run_id}.log"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                self._log = _open_private(path)
            except OSError:
                pass
            if self._log != subprocess.DEVNULL:
                self.path = path
        self.started = time.monotonic()
        self.proc: Optional[subprocess.Popen] = None

    def popen(self, cmd: list, cwd: str) -> subprocess.Popen:
        """Start the agent with stdout and stderr in this run's log."""
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=self._log, stderr=subprocess.STDOUT)
        return self.proc

    def stop(self) -> None:
        """End a still-running agent and reap it, then close the log. Never raises.

        A claim must not be reported terminal, and its worktree removed, while
        the agent is still executing in it.
        """
        proc = self.proc
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        except OSError:
            pass
        self.close()

    def close(self) -> None:
        """Close the log. Never raises: a failed flush must not cost the claim its terminal update."""
        try:
            if hasattr(self._log, "close") and not self._log.closed:
                self._log.close()
        except OSError:
            pass

    def fields(self, plan: dict) -> dict:
        """The run-record fields `/api/mesh/claim/update` stores next to the claim state."""
        self.close()
        return {
            "run_id": self.run_id,
            "duration_s": round(time.monotonic() - self.started, 1),
            "exit_code": getattr(self.proc, "returncode", None),
            "error_code": error_code(plan),
        }


def run_agent(make_cmd: Callable[[], list], cwd: str, base_dir: Path, run_id: str,
              plan: dict, wait: Callable[[subprocess.Popen, dict], None]) -> Optional[RunRecord]:
    """Build the record and the command, run the agent; return the record, or None.

    Never raises. Any failure — building the record, building the command (the
    prompt), starting or waiting on the agent — lands in `plan` as a failed
    state, so the caller always reaches its terminal claim update and cleanup.
    """
    rec = None
    try:
        rec = RunRecord(run_id, base_dir)
        wait(rec.popen(make_cmd(), cwd), plan)
    except Exception as exc:  # noqa: BLE001 — reported as the claim's failure, never re-raised
        plan["state"] = "failed"
        plan["error"] = str(exc)
        plan["error_code"] = "runner_exception_os" if isinstance(exc, OSError) else "runner_exception"
        if rec is not None:
            rec.stop()
    return rec


def fields(rec: Optional[RunRecord], plan: dict) -> dict:
    """The fields to report for `rec`, or just the error code. Never raises."""
    if rec is not None:
        try:
            return rec.fields(plan)
        except Exception:  # noqa: BLE001 — the terminal update must still go out
            pass
    return {"error_code": error_code(plan)}


def remove_worktree(repo_dir: Path, worktree: Path) -> None:
    """`git worktree remove --force`, never raising: cleanup failing must not strand the claim.

    Any exception, not only OSError: a claim id with a NUL byte makes subprocess
    raise ValueError before git ever starts.
    """
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, check=False,
        )
    except Exception:  # noqa: BLE001 — cleanup is best-effort; the terminal update is not
        pass
