"""What the runner loop does when it may not claim, or has nothing to claim (RA-7802).

Split out of runner.py for its 300-line gate. `rt` is the runner module's own
namespace, as plan_lane takes it, so a test that patches the runner still
reaches these functions.
"""
from __future__ import annotations

import json
import os
import sys
import time
from types import SimpleNamespace

import agent_sandbox
import breadcrumb
import node_health
import self_update
import version_gate

HELD = -1  # before_claim's "held this turn, already waited": loop again, claim nothing

class Log:
    """What every runner log line carries (estate audit 30/09, rank 18).

    The Mini logged `{"status": "BLOCKED", "reason": "agent timed out"}` twenty times
    with no time on any line, and an outage returned the same `claims: 0` as an empty
    queue. Each line now says when, why the node is held, what the last poll found
    (unavailable | rejected | empty | assigned) and when the server last answered.
    """

    def __init__(self, alert_after: int | None = None, clock=time.time):
        if alert_after is None:  # read per runner, not once per interpreter
            alert_after = int(os.environ.get("MESH_HOLD_ALERT_AFTER", "10"))
        self._alert_after, self._clock = max(1, alert_after), clock
        self.holds = 0                   # consecutive loop turns spent held
        self.poll: str | None = None
        self.last_contact: int | None = None

    def polled(self, outcome: str) -> None:
        """One poll ran, so the node is not held."""
        self.holds, self.poll = 0, outcome

    def contacted(self) -> None:
        """The server answered a call successfully; a failed one never moves this."""
        self.last_contact = int(self._clock())

    def line(self, health: node_health.NodeHealth | None, **fields) -> str:
        held = health is not None and health.state != "healthy"
        record = {"ts": int(self._clock()), **fields, "hold_reason": (health.reason or None) if held else None,
                  "claude_config_dir": agent_sandbox.config_dir()}  # which login the agent runs as
        if self.poll:
            record.update(poll=self.poll, last_contact=self.last_contact)
        return json.dumps(record)

    def alert_due(self) -> bool:
        """Every MESH_HOLD_ALERT_AFTER (default 10) consecutive holds."""
        return self.holds % self._alert_after == 0


def hold(rt: SimpleNamespace, health: node_health.NodeHealth, once: bool) -> int | None:
    """Report a node that may not claim. An exit code for --once, else None after the poll wait."""
    rt.write_state(None, health.state, hold_reason=health.reason or None)  # heartbeat reports the hold
    rt.LOG.holds += 1
    print(rt.LOG.line(health, runner=rt.HOST, status=health.state.upper(), reason=health.reason,
                      holds=rt.LOG.holds), flush=True)
    if rt.LOG.alert_due():
        print(rt.LOG.line(health, runner=rt.HOST, status="ALERT", holds=rt.LOG.holds,
                          alert=f"held {rt.LOG.holds} polls in a row, claiming nothing"),
              file=sys.stderr, flush=True)
    if once:
        return 1
    rt.time.sleep(rt.POLL_INTERVAL)
    return None


def idle(rt: SimpleNamespace, updater: self_update.Updater | None,
         health: node_health.NodeHealth, work: list) -> int | None:
    """Idle and healthy: move to new runner code. An exit code (3: restart on it), or None."""
    if updater is not None and not work and health.state == "healthy" and updater.due():
        outcome = _try_update(rt, updater, health)
        if outcome == "updated":
            return 3
        if outcome.startswith("stuck"):
            return _stuck(rt, outcome)
    held = health.state != "healthy"
    rt.write_state(None, health.state if held else "idle", hold_reason=(health.reason or None) if held else None)
    return None


def _try_update(rt: SimpleNamespace, updater: self_update.Updater,
                health: node_health.NodeHealth | None) -> str:
    """One Updater attempt, logged and kept in the breadcrumb as last_update."""
    outcome = updater.try_update()
    breadcrumb.remember(rt.STATE_FILE, "last_update", {"outcome": outcome, "ts": int(time.time())})
    print(rt.LOG.line(health, runner=rt.HOST, status="SELF_UPDATE", outcome=outcome), flush=True)
    return outcome


def _stuck(rt: SimpleNamespace, outcome: str) -> int:
    """HEAD could not return to proven code. Exit 0 alone does not keep a node down
    (the PC's task restarts it every 5 min; any node restarts on reboot), so leave a
    marker outside the repo that every later start obeys. Until it is written, never
    exit: a restart with no marker would claim on that code."""
    rt.write_state(None, "stuck")
    while True:
        try:
            self_update.mark_stuck(rt.stuck_file(), outcome)
            return 0
        except OSError:
            rt.time.sleep(rt.POLL_INTERVAL)


def _held(rt: SimpleNamespace, state: str, reason: str, once: bool) -> int:
    """Claim nothing this turn and say why. 1 for --once, else HELD after the poll wait."""
    rt.write_state(None, state, hold_reason=reason)
    rt.LOG.holds += 1
    print(rt.LOG.line(None, runner=rt.HOST, status=state.upper(), reason=reason, holds=rt.LOG.holds), flush=True)
    if once:
        return 1
    rt.time.sleep(rt.POLL_INTERVAL)
    return HELD


def before_claim(rt: SimpleNamespace, updater: self_update.Updater | None, once: bool) -> int | None:
    """None: this node may claim. Else an exit code, or HELD. Runs only between claims, so a
    running claim is never interrupted. HARD_STOP holds and never exits (08/11/2026): launchd
    restarts only a failed runner, so the old exit 0 left the node dead after the file went."""
    breadcrumb.refresh_local_edits(rt.CODE_DIR)
    if rt.killed():
        return _held(rt, "hard_stop", "hard stop armed; remove ~/.claude/HARD_STOP and this runner resumes", once)
    gate = rt.GATE
    if gate is None:
        return None
    verdict = gate.check()
    if verdict.status == "current":
        return None
    if verdict.status != "outdated":
        return _held(rt, "version-unknown", verdict.reason, once)
    if verdict.fetched or gate.blocker is None:  # one attempt per fresh check, not every poll
        code = _update_now(rt, updater, gate, verdict)
        if code is not None:
            return code
    return _held(rt, "outdated", gate.blocker or verdict.reason, once)


def _update_now(rt: SimpleNamespace, updater: self_update.Updater | None,
                gate: version_gate.VersionGate, verdict: version_gate.Verdict) -> int | None:
    """Outdated and idle: try the existing Updater now. An exit code, or None with gate.blocker set."""
    if updater is None:
        gate.blocker = ("outdated: self-update is off on this node (MESH_SELF_UPDATE=0); "
                        "move the runtime to origin/main by hand, then restart the runner")
        return None
    rt.write_state(None, "updating")
    outcome = _try_update(rt, updater, None)
    if outcome == "updated":
        return 3
    if outcome.startswith("stuck"):
        return _stuck(rt, outcome)
    if outcome == "current" and self_update.runtime_version(rt.CODE_DIR) == verdict.approved:
        return 3  # HEAD already is the approved commit; only this process is old: restart onto it
    gate.blocker = version_gate.blocker(outcome)
    return None
