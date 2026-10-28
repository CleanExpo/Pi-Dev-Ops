"""C5 (w_cae13c9af03d): the real Guardian watcher reports the true sum across a machine-ledger reset.

argv: repo root, repo python, watcher script path. Everything runs under a throwaway HOME.
Writes, through production code with fake transports, twice:
  - one client.send call that the fake answers with 1,000 input tokens;
  - one shadow reserve_call/finish_call pair into a legacy ledger (mirrored into the canonical one), settled at 2,000 tokens.
Between the two runs the canonical ledger is deleted (a reset), so the second run's canonical rows reuse row ids 1
and 2 at the same amounts. The first run's mirrored legacy row then shares spend_id=2 and its amount with a
different call; only the call id tells them apart. The old rule (id + amount) hides it.
Plus one old-style legacy ledger (no spend_id column, as old code writes it) holding one unmirrored row of $0.25.
Expected watcher total = (1000 + 2000) * 0.042e-6 (new canonical) + 2000 * 0.042e-6 (first legacy row, a different
call) + 0.25 (old ledger), with nothing reported UNKNOWN."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime

ROOT, PY, WATCHER = sys.argv[1], sys.argv[2], sys.argv[3]
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

with tempfile.TemporaryDirectory(prefix="jev-seam-", dir="/tmp") as base:
    home = os.path.join(base, "home")
    ops = os.path.join(base, "ops")
    os.makedirs(home)
    os.makedirs(ops)
    with open(os.path.join(ops, "jobs.json"), "w") as f:
        json.dump({"jobs": []}, f)
    canonical = os.path.join(base, "spend.sqlite")
    legacy = os.path.join(base, "skill-router-ledger.sqlite")
    old = os.path.join(base, "old-ledger.sqlite")
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": "/tmp", "JEV_SPEND_LEDGER": canonical}
    for run in ("first", "after-reset"):
        if run == "after-reset":
            os.unlink(canonical)
        r = subprocess.run([PY, "-c", WRITER, ROOT, legacy], env=env, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"writer ({run}) failed:", r.stdout, r.stderr)
            sys.exit(1)
    ldb = sqlite3.connect(legacy)
    ids = [r[0] for r in ldb.execute("SELECT spend_id FROM calls ORDER BY id")]
    ldb.close()
    if len(ids) != 2 or ids[0] != ids[1]:
        print("the reset did not reuse the mirrored row id, so this check proves nothing:", ids)
        sys.exit(1)
    day = datetime.now(UTC).date().isoformat()
    db = sqlite3.connect(old)
    db.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, reserved_usd REAL NOT NULL, actual_usd REAL, "
               "input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("INSERT INTO calls(day, reserved_usd, status, created_at) VALUES (?, 0.25, 'attempted', ?)",
               (day, datetime.now(UTC).isoformat()))
    db.commit()
    db.close()
    wenv = dict(env, JEV_WATCH_CANONICAL=canonical, JEV_WATCH_LEGACY=f"{legacy}:{old}",
                JEV_WATCH_OPS=ops, JEV_WATCH_STATE=os.path.join(base, "state.json"), JEV_WATCH_DRY="1")
    w = subprocess.run(["/opt/homebrew/bin/python3", WATCHER], env=wenv, capture_output=True, text=True, timeout=120)
    summary = None
    for line in w.stdout.splitlines():
        if line.startswith("{") and '"spent"' in line:
            summary = json.loads(line)
    if summary is None:
        print("watcher printed no summary line:", w.returncode, w.stdout[-800:], w.stderr[-800:])
        sys.exit(1)
    expected = (1000 + 2000 + 2000) * PRICE + 0.25
    print(json.dumps(summary, sort_keys=True))
    print(f"expected {expected:.9f}")
    good = abs(summary["spent"] - expected) < 1e-9 and not summary.get("unknown") and summary.get("ledger") == canonical
    sys.exit(0 if good else 1)
