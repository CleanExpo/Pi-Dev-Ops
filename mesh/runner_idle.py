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

import node_health
import self_update

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
        record = {"ts": int(self._clock()), **fields, "hold_reason": (health.reason or None) if held else None}
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
        outcome = updater.try_update()
        print(rt.LOG.line(health, runner=rt.HOST, status="SELF_UPDATE", outcome=outcome))
        if outcome == "updated":
            return 3
        if outcome.startswith("stuck"):
            # HEAD could not return to proven code. Exit 0 alone does not keep a node
            # down (the PC's task restarts it every 5 min; any node restarts on reboot),
            # so leave a marker outside the repo that every later start obeys. Until it
            # is written, never exit: a restart with no marker would claim on that code.
            rt.write_state(None, "stuck")
            while True:
                try:
                    self_update.mark_stuck(rt.stuck_file(), outcome)
                    return 0
                except OSError:
                    rt.time.sleep(rt.POLL_INTERVAL)
    held = health.state != "healthy"
    rt.write_state(None, health.state if held else "idle", hold_reason=(health.reason or None) if held else None)
    return None
