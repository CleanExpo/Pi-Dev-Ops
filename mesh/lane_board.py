"""One board line per lane decision, written to the Mini's jobs.json (UNI-3291).

The board is `/Volumes/Mini Mini 2T Storage/ops/jobs.json` on the Mac Mini. The PC
reaches it over SSH, as the PC board worker does (`pc-board.py`), and edits it with the
same convention: flock on `jobs.json.lock`, a backup in `.board-bak`, then an atomic
replace. Each lane gets ONE job row, `PC-LANE-<LANE>`, that says what happened last:

    resumed     status done   "resumed on PC from step X"
    handed_off  status todo   assigned_to Mini/MacBook, "handed to Mini from step X"
    parked      status open   P1 alert, "parked after N attempts"

Delivery is never assumed. The supervisor saves each line inside the lane's own
state file in the same write as the decision, and removes it only when the Mini
confirms the write, so an unreachable Mini delays the line and never loses it.
Re-sending is safe: each event carries a uid and the Mini skips one it already has.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_proc  # noqa: E402

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
BOARD_HOST = os.environ.get("LANE_BOARD_HOST", "mini")
OK = "LANE-BOARD-OK"

# Runs on the Mini under its own python3. Kept free of f-strings so it can be read as-is.
REMOTE = r'''
import datetime, fcntl, json, os, shutil, sys, time
B = os.environ.get("LANE_BOARD", "/Volumes/Mini Mini 2T Storage/ops/jobs.json")
BAK = os.path.join(os.path.dirname(B), ".board-bak")
STATUS = {"resumed": "done", "handed_off": "todo", "parked": "open"}
def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M+10:00")
def apply(d, ev):
    j = next((x for x in d["jobs"] if x.get("id") == ev["id"]), None)
    if j is None:
        j = {"id": ev["id"], "created": now()}
        d["jobs"].append(j)
    if ev["uid"] in j.get("event_uids", []):
        return False
    j.update(title=ev["text"], owner="PC lane supervisor", status=STATUS[ev["action"]],
             priority="P3" if ev["action"] == "resumed" else "P1", updated=now(),
             note=ev["note"], lane=ev["lane"], lane_action=ev["action"])
    if ev.get("linear"):
        j["linear"] = ev["linear"]
    if ev["action"] == "handed_off":
        j["assigned_to"] = ev["target"]
        j["next_action"] = ev["note"]
    if ev["action"] == "parked":
        j["blocker"] = ev["text"]
    j["event_uids"] = (j.get("event_uids", []) + [ev["uid"]])[-20:]
    return True
with open(B + ".lock", "w") as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    d = json.load(open(B))
    if any([apply(d, ev) for ev in EVENTS]):
        os.makedirs(BAK, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + "-lane-" + str(time.time_ns() % 10**9)
        shutil.copy2(B, os.path.join(BAK, "jobs.json.bak-" + stamp))
        tmp = B + ".lane.tmp"
        json.dump(d, open(tmp, "w"), indent=1)
        os.replace(tmp, B)
print("LANE-BOARD-OK")
'''


def remote_script(events: list) -> str:
    """The Mini-side program with the events embedded as a Python literal (no shell quoting)."""
    return "import json\nEVENTS = json.loads(" + repr(json.dumps(events)) + ")\n" + REMOTE


def ssh_send(events: list) -> tuple:
    script = remote_script(events)
    rc, out = lane_proc.run_quiet(SSH + [BOARD_HOST, "/usr/bin/python3", "-"], script, timeout=60)
    return rc == 0 and OK in out, out


def board_event(st: dict, action: str, now: float, target: str = "", why: str = "") -> dict:
    """The one wording of a lane's board line. `uid` makes a resend recognisable."""
    lane, step = st["lane"], st.get("step", "start")
    who = f"{lane} ({st['linear_id']})" if st.get("linear_id") else lane
    tail = {"resumed": "resumed on PC", "handed_off": f"handed to {target}",
            "parked": f"parked, needs a person: {why}"}[action]
    note = (f"Lane folder {st.get('resume', {}).get('cwd')} on {st.get('host')}. Last step: {step}. "
            f"Steps done: {', '.join(st.get('steps_done', [])) or 'none'}. Saved command and history: "
            f"lane-state.json in that folder.")
    if action == "handed_off":
        note = f"Resume lane {lane} on {target} from step {step}. " + note
    return {"id": "PC-LANE-" + re.sub(r"[^A-Z0-9]+", "-", lane.upper()).strip("-"),
            "uid": f"{lane}:{action}:{int(now)}:{st.get('attempts', 0)}", "lane": lane,
            "action": action, "target": target, "linear": st.get("linear_id"),
            "text": f"PC lane {who} stopped at step {step}: {tail}", "note": note}
