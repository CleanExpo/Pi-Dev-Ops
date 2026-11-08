"""Does this runner run the approved code? Asked before every claim (fleet version gate, 08/11/2026).

APPROVED VERSION, the one definition: the commit at the tip of `main` on origin.
`main` only moves through a merged pull request with required checks and a human
merge, so an unmerged branch can never become the approved version, however new
it is. What other branches hold is irrelevant here. The tip is read through
`self_update.fetch_main`, into self_update's private ref `refs/mesh-self-update/main`:
there is one fetch path, not two.

Why it exists. On 08/11/2026 the Mini claimed RA-7487 while five commits behind
main: the version was looked at only every 15 idle minutes and claiming never
asked. Two runtimes with local edits refused every update into one log line and
kept claiming on old code. `VersionGate.check()` gives the runner, before every
claim and at startup, (running, approved, status, reason) with status one of:

  * ``current``  — running == approved: claim as before;
  * ``outdated`` — try the existing Updater now; if it refuses, claim nothing and
    say which blocker and what to do (``blocker()``);
  * ``unknown``  — the tip or the running commit cannot be read (offline, no
    access): claim nothing. Never cached, so a machine that reconnects catches up
    by itself on the next poll.

A fetched answer is cached for MESH_VERSION_CHECK_SECONDS (default 300) so a 30 s
poll loop does not hit origin every turn. MESH_VERSION_GATE=0 turns the gate off.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import self_update  # noqa: E402

CHECK_SECONDS = float(os.environ.get("MESH_VERSION_CHECK_SECONDS", "300"))
ENABLED = os.environ.get("MESH_VERSION_GATE", "1") != "0"
_SHA = re.compile(r"^[0-9a-f]{40}$")

# Updater outcome prefix -> "<blocker>; <next action>". The tile splits on the first "; ".
_BLOCKERS: tuple[tuple[str, str], ...] = (
    ("update refused: runtime has local edits",
     "outdated: runtime has local edits; checkpoint them, then restore the runtime to HEAD"),
    ("update refused: runtime is on a branch",
     "outdated: runtime is on a branch, not detached at main; checkpoint any work, then check out origin/main detached"),
    ("update refused: origin/main is not a fast-forward",
     "outdated: runtime has commits main does not; checkpoint them on a branch, then check out origin/main detached"),
    ("update refused: an agent this node could not stop",
     "outdated: an agent this node could not stop may still be running; stop it, and the next check retries"),
    ("update refused: HEAD moved during the update",
     "outdated: HEAD moved during the update; the next check retries"),
    ("update failed: fetch", "outdated: could not fetch main for the update; the next check retries"),
)


def sha_or_none(value: object) -> str | None:
    """A full commit id, or None: "unknown", "" and anything else are not facts."""
    text = str(value or "").strip()
    return text if _SHA.match(text) else None


def blocker(outcome: str) -> str:
    """Why an outdated runtime did not update, and what a person does next."""
    for prefix, reason in _BLOCKERS:
        if outcome.startswith(prefix):
            return reason
    if outcome.startswith("rolled back: "):
        return (f"outdated: main failed its preflight on this machine ({outcome[13:200]}); "
                "fix it on main, and the next check retries")
    return f"outdated: {outcome[:200]}; the next check retries"


def local_edits(repo: Path, run: Callable[..., subprocess.CompletedProcess] | None = None) -> int | None:
    """How many tracked files differ from HEAD in the runtime, or None if git cannot say."""
    try:
        done = (run or subprocess.run)(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                                       capture_output=True, text=True, check=False, timeout=10)
        if done.returncode != 0:
            return None
        return len([line for line in done.stdout.splitlines() if line.strip()])
    except Exception:  # noqa: BLE001 — unknown is null, never a guessed count
        return None


@dataclass(frozen=True)
class Verdict:
    running: str | None
    approved: str | None
    status: str          # current | outdated | unknown
    reason: str
    fetched: bool = True  # False: served from the cache


class VersionGate:
    """Compares the commit this process runs with the approved one, origin main's tip."""

    def __init__(self, repo: Path, running: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 clock: Callable[[], float] = time.monotonic, every: float = CHECK_SECONDS):
        self._repo, self._running, self._run = Path(repo), sha_or_none(running), run
        self._clock, self._every, self._at = clock, every, 0.0
        self.last: Verdict | None = None
        self.blocker: str | None = None   # the last refusal, held while the cached verdict stands

    def check(self) -> Verdict:
        """The current verdict. An unknown one is never served from the cache."""
        if self.last and self.last.status != "unknown" and self._clock() - self._at < self._every:
            self.last = replace(self.last, fetched=False)
            return self.last
        self.last, self._at = self._read(), self._clock()
        return self.last

    def _read(self) -> Verdict:
        if not self._running:
            return Verdict(None, None, "unknown",
                           "version-unknown: git cannot read the commit this runner runs; re-checked every poll")
        try:
            approved = sha_or_none(self_update.fetch_main(self._repo, self._run))
        except (OSError, subprocess.SubprocessError):
            approved = None
        if not approved:
            return Verdict(self._running, None, "unknown",
                           "version-unknown: could not read origin/main (offline or no access); re-checked every poll")
        if approved == self._running:
            self.blocker = None
            return Verdict(self._running, approved, "current", "")
        return Verdict(self._running, approved, "outdated",
                       f"outdated: running {self._running[:12]}, approved {approved[:12]} (origin/main)")
