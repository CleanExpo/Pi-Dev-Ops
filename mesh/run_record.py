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
_RUN_ID = re.compile(r"[0-9a-f]{8}")
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


def _describe(exc: BaseException) -> str:
    """The exception's message for local diagnostics. Never raises: its `__str__` is somebody else's code."""
    try:
        return str(exc)
    except Exception:  # noqa: BLE001 — an unprintable exception is still a failure to record
        return "unprintable exception"


def _attempt(action: Callable[[], Any], held: list) -> bool:
    """Run one shutdown step; True if it completed. Each step is attempted even
    when the one before it failed. An Exception is absorbed; an interrupt
    (KeyboardInterrupt, SystemExit) is appended to `held`, for the caller to
    re-raise once every step has been attempted."""
    try:
        action()
        return True
    except Exception:  # noqa: BLE001 — shutdown is best-effort, step by step
        return False
    except BaseException as exc:  # held, not lost: re-raised after the agent is reaped
        held.append(exc)
        return False


def _open_private(path: Path) -> Any:
    """Create `path` new, owner-only from the first byte, or return DEVNULL.

    O_EXCL: an existing file at this path — an earlier run's transcript under a
    repeated id, or a hard link planted there — is never opened, let alone
    truncated. The run then goes ahead without a log. The mode is set at
    creation, so there is no window with the umask's wider mode. Any failure
    after creating the file removes it.
    """
    fd = -1
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
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
        self.reaped: Optional[bool] = None  # set by stop(): False = the agent may still be running

    def popen(self, cmd: list, cwd: str) -> subprocess.Popen:
        """Start the agent with stdout and stderr in this run's log.

        An Exception from Popen means no agent is running: Popen reaps a child
        that failed to exec. An interrupt can land after the child started but
        before Popen returned its handle (review round 18), leaving an agent this
        record cannot see; stop() then reports it as not reaped.
        """
        try:
            self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=self._log, stderr=subprocess.STDOUT)
        except Exception:
            raise
        except BaseException:
            self.unseen_agent = True
            raise
        return self.proc

    def stop(self) -> None:
        """End a still-running agent and reap it, then close the log.

        A claim must not be reported terminal, and its worktree removed, while
        the agent is still executing in it. Never raises an Exception. An
        interrupt arriving during any step does not cut shutdown short: it is
        held until every step has been attempted, then re-raised.
        """
        held: list = []
        proc = self.proc
        if proc is None and getattr(self, "unseen_agent", False):
            self.reaped = False  # an agent may be running with no handle to stop it
        if proc is not None:
            exited: list = []
            _attempt(lambda: exited.append(proc.poll() is not None), held)
            if exited != [True]:  # still running, or cannot tell
                _attempt(proc.terminate, held)
                if not _attempt(lambda: proc.wait(timeout=10), held):
                    _attempt(proc.kill, held)
                    _attempt(proc.wait, held)
            gone: list = []
            _attempt(lambda: gone.append(proc.poll() is not None), held)
            self.reaped = gone == [True]
        _attempt(self.close, held)
        if held:
            raise held[0]

    def close(self) -> None:
        """Close the log. Never raises: a failed flush must not cost the claim its terminal update."""
        try:
            if hasattr(self._log, "close") and not self._log.closed:
                self._log.close()
        except Exception:  # noqa: BLE001 — any close failure, not only OSError
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
              plan: dict, wait: Callable[[subprocess.Popen, dict], None],
              holder: Optional[list] = None) -> Optional[RunRecord]:
    """Build the record and the command, run the agent; return the record, or None.

    Never raises an Exception. Any failure — building the record, building the
    command (the prompt), starting or waiting on the agent — lands in `plan` as
    a failed state, so the caller always reaches its terminal claim update and
    cleanup. An interrupt (KeyboardInterrupt, SystemExit) is not swallowed: the
    agent is stopped and reaped first, then the interrupt propagates, so the
    caller's cleanup never runs while the agent is still executing. The stop
    sits in `finally`, so nothing a handler does can skip it. The record is
    appended to `holder` as soon as it exists, so a caller whose call is cut
    short by an interrupt still learns whether the agent was reaped.
    """
    rec = None
    finished = False
    try:
        rec = RunRecord(run_id, base_dir)
        if holder is not None:
            holder.append(rec)
        wait(rec.popen(make_cmd(), cwd), plan)
        finished = True
    except Exception as exc:  # noqa: BLE001 — reported as the claim's failure, never re-raised
        plan["state"] = "failed"
        plan["error_code"] = "runner_exception_os" if isinstance(exc, OSError) else "runner_exception"
        plan["error"] = _describe(exc)
    except BaseException:
        plan["state"] = "failed"
        plan["error_code"] = "runner_exception"
        raise
    finally:
        if rec is not None and not finished:
            rec.stop()
    return rec


def unreaped(rec: Optional[RunRecord]) -> bool:
    """True if stop() could not prove the agent exited: it may still be running in the worktree."""
    return rec is not None and getattr(rec, "reaped", None) is False


def fields(rec: Optional[RunRecord], plan: dict) -> dict:
    """The fields to report for `rec`, or just the error code. Never raises."""
    if rec is not None:
        try:
            return rec.fields(plan)
        except Exception:  # noqa: BLE001 — the terminal update must still go out
            pass
    return {"error_code": error_code(plan)}


def terminal(rec: Optional[RunRecord], plan: dict) -> dict:
    """The terminal claim update: state plus run record. Never raises.

    A plan with no state means something escaped `run_agent`; it is reported as
    a failure rather than left for the claim to sit `working`.
    """
    if "state" not in plan:
        plan.update(state="failed", error_code="runner_exception")
    return {"state": plan["state"], **fields(rec, plan)}
