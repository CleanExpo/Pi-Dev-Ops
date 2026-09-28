"""What the runner loop does when it may not claim, or has nothing to claim (RA-7802).

Split out of runner.py for its 300-line gate. `rt` is the runner module's own
namespace, as plan_lane takes it, so a test that patches the runner still
reaches these functions.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import node_health
import self_update


def hold(rt: SimpleNamespace, health: node_health.NodeHealth, once: bool) -> int | None:
    """Report a node that may not claim. An exit code for --once, else None after the poll wait."""
    rt.write_state(None, health.state)  # the heartbeat reports blocked/quarantined
    print(json.dumps({"runner": rt.HOST, "status": health.state.upper(), "reason": health.reason}))
    if once:
        return 1
    rt.time.sleep(rt.POLL_INTERVAL)
    return None


def idle(rt: SimpleNamespace, updater: self_update.Updater | None,
         health: node_health.NodeHealth, work: list) -> int | None:
    """Idle and healthy: move to new runner code. An exit code (3: restart on it), or None."""
    if updater is not None and not work and health.state == "healthy" and updater.due():
        outcome = updater.try_update()
        print(json.dumps({"runner": rt.HOST, "status": "SELF_UPDATE", "outcome": outcome}))
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
    rt.write_state(None, "idle" if health.state == "healthy" else health.state)
    return None
