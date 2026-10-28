"""C5 (w_77f2243a8e50): the reviewed Guardian watcher, at one exact skills-library commit, over ledgers this code wrote.

argv: repo root, repo python, skills-library repo path, watcher commit SHA. The watcher and its jobs_lock.py are
extracted with `git show <sha>:<path>` into a temp dir, so the check proves that commit, not whatever a worktree
holds at verify time. Everything runs under a throwaway HOME.

Each writer run sends, through production code with fake transports:
  - one client.send call answered with 1,000 input tokens (machine ledger only: nothing mirrors it);
  - one shadow reserve_call/finish_call pair into a legacy ledger (mirrored), settled at 2,000 tokens.
Plus an old-style legacy ledger (no spend_id column) holding one unmirrored $0.25 row.

Watcher run 1, after the first writer run: the true total, (1000 + 2000) * PRICE + 0.25, nothing UNKNOWN.
Then the machine ledger is deleted (a reset) and the writer runs again: row ids 1 and 2 are reused at the same
amounts. True spend is now (1000 + 2000) * 2 * PRICE + 0.25, but the first client.send row is gone with the file
and no ledger can show it. Watcher run 2 must therefore report the machine ledger UNKNOWN, with the
W-TYPESAFE-CAP-UNKNOWN row naming a reset, and a lower bound of (1000 + 2000 + 2000) * PRICE + 0.25: the lost call
is the only missing amount, and the first run's mirrored row (same row id, same amount, different call) still counts."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime

ROOT, PY, WREPO, WSHA = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
PRICE = 0.042e-6
WRITER = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from jev_platform import client
from scripts import mission_control_jev_shadow as sh
legacy = Path(sys.argv[2])
budget = client.Budget(1.0, 60)
out = client.send({"state": "s", "model": "jev-latest", "questions": {}},
                  lambda body, timeout: (200, {"usage": {"input_tokens": 1000}, "answers": {}}, None), budget)
assert "data" in out, out
cid = sh.reserve_call(legacy, sh.RESERVED_INPUT_TOKENS_PER_CALL)
assert cid is not None
sh.finish_call(legacy, cid, "answered", 2000)
'''


def fail(*msg):
    print(*msg)
    sys.exit(1)


def extract(dest):
    for name in ("jev-cap-watcher.py", "jobs_lock.py"):
        r = subprocess.run(["git", "-C", WREPO, "show", f"{WSHA}:skills/guardian/scripts/{name}"],
                           capture_output=True, check=False)
        if r.returncode != 0:
            fail(f"cannot read {name} at {WSHA}:", r.stderr.decode()[-300:])
        with open(os.path.join(dest, name), "wb") as f:
            f.write(r.stdout)
    return os.path.join(dest, "jev-cap-watcher.py")


def write(env, legacy, run):
    r = subprocess.run([PY, "-c", WRITER, ROOT, legacy], env=env, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        fail(f"writer ({run}) failed:", r.stdout, r.stderr)


def watch(watcher, wenv):
    w = subprocess.run(["/opt/homebrew/bin/python3", watcher], env=wenv, capture_output=True, text=True, timeout=120)
    lines = [json.loads(line) for line in w.stdout.splitlines() if line.startswith("{") and '"spent"' in line]
    if len(lines) != 1:
        fail("watcher printed no single summary line:", w.returncode, w.stdout[-800:], w.stderr[-800:])
    print(json.dumps(lines[0], sort_keys=True))
    return lines[0]


def old_ledger(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, reserved_usd REAL NOT NULL, actual_usd REAL, "
               "input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("INSERT INTO calls(day, reserved_usd, status, created_at) VALUES (?, 0.25, 'attempted', ?)",
               (datetime.now(UTC).date().isoformat(), datetime.now(UTC).isoformat()))
    db.commit()
    db.close()


with tempfile.TemporaryDirectory(prefix="jev-seam-", dir="/tmp") as base:
    home, ops, wdir = (os.path.join(base, n) for n in ("home", "ops", "watcher"))
    for d in (home, ops, wdir):
        os.makedirs(d)
    print("watcher commit:", WSHA)
    watcher = extract(wdir)
    with open(os.path.join(ops, "jobs.json"), "w") as f:
        json.dump({"jobs": []}, f)
    canonical, legacy, old = (os.path.join(base, n) for n in ("spend.sqlite", "skill-router-ledger.sqlite", "old-ledger.sqlite"))
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": "/tmp", "JEV_SPEND_LEDGER": canonical}
    wenv = dict(env, JEV_WATCH_CANONICAL=canonical, JEV_WATCH_LEGACY=f"{legacy}:{old}",
                JEV_WATCH_OPS=ops, JEV_WATCH_STATE=os.path.join(base, "state.json"), JEV_WATCH_DRY="1")
    old_ledger(old)
    write(env, legacy, "first")
    first = watch(watcher, wenv)
    true_first = (1000 + 2000) * PRICE + 0.25
    if abs(first["spent"] - true_first) > 1e-9 or first.get("unknown") or first.get("ledger") != canonical:
        fail(f"run 1: expected exactly {true_first:.9f} and nothing UNKNOWN")
    os.unlink(canonical)
    write(env, legacy, "after-reset")
    ldb = sqlite3.connect(legacy)
    ids = [r[0] for r in ldb.execute("SELECT spend_id FROM calls ORDER BY id")]
    ldb.close()
    if len(ids) != 2 or ids[0] != ids[1]:
        fail("the reset did not reuse the mirrored row id, so this check proves nothing:", ids)
    second = watch(watcher, wenv)
    bound = (1000 + 2000 + 2000) * PRICE + 0.25
    blocker = next((j["blocker"] for j in json.load(open(os.path.join(ops, "jobs.json")))["jobs"]
                    if j["id"] == "W-TYPESAFE-CAP-UNKNOWN"), "")
    print(f"run 2: expected lower bound {bound:.9f}, machine ledger UNKNOWN, blocker names a reset")
    good = (abs(second["spent"] - bound) < 1e-9 and second.get("unknown") == [canonical]
            and canonical in blocker and "reset" in blocker)
    sys.exit(0 if good else 1)
