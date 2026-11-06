"""A do-nothing lane that proves the lane supervisor works across a kill or a reboot (UNI-3291).

    pythonw lane_dummy.py --dir C:\\agent-work\\uni-3291-dummy-lane --proof C:\\agent-work\\.lane-supervisor\\dummy-lane

First start: saves its state as `running` (lane_state.begin) and waits, using no CPU.
When the supervisor relaunches it (LANE_RESUMED=1) it writes what it can prove:

    kill-proof-<n>.json   relaunched with no reboot since the lane first started
    reboot-proof.json     the machine booted after the lane first started, and the
                          relaunch came <resumed_epoch - boot_epoch> seconds after boot

After a reboot proof it marks itself done and exits. Otherwise it waits up to 7 days
(or until a STOP file appears in its folder) and then marks itself done.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_proc  # noqa: E402
import lane_state  # noqa: E402

WAIT_SECONDS = 7 * 24 * 3600
STEP = "waiting-for-interruption"


def write_proof(lane_dir: str, proof_dir: Path, started_now: float) -> bool:
    """Record this relaunch. True when it proves a reboot (the lane is then finished)."""
    st = lane_state.load(lane_dir)
    boot = lane_proc.boot_epoch()
    rec = {"lane": st["lane"], "lane_started_epoch": st["created_epoch"], "boot_epoch": boot,
           "resumed_epoch": started_now, "seconds_after_boot": round(started_now - boot, 1),
           "attempt": st.get("attempts"), "pid": os.getpid(), "resume_step": os.environ.get("LANE_RESUME_STEP"),
           "history": st.get("history", [])[-5:]}
    proof_dir.mkdir(parents=True, exist_ok=True)
    rebooted = boot > st["created_epoch"]
    name = "reboot-proof.json" if rebooted else f"kill-proof-{st.get('attempts')}.json"
    (proof_dir / name).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rebooted


def main(argv: list = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True)
    p.add_argument("--proof", required=True)
    a = p.parse_args(argv)
    started_now = time.time()
    Path(a.dir).mkdir(parents=True, exist_ok=True)
    me = [sys.executable, os.path.abspath(__file__), "--dir", a.dir, "--proof", a.proof]
    lane_state.begin(a.dir, os.getpid(), me, STEP, "UNI-3291",
                     token=os.environ.get("LANE_LAUNCH_TOKEN"))
    if os.environ.get("LANE_RESUMED") == "1" and write_proof(a.dir, Path(a.proof), started_now):
        lane_state.update(a.dir, state=lane_state.DONE, note="reboot proof written", finished_epoch=time.time())
        return 0
    while time.time() - started_now < WAIT_SECONDS and not (Path(a.dir) / "STOP").exists():
        time.sleep(30)
    lane_state.update(a.dir, state=lane_state.DONE, note="dummy wait ended", finished_epoch=time.time())
    return 0


if __name__ == "__main__":
    sys.exit(main())
