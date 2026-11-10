#!/usr/bin/env python3
"""Orchestrator v1 for the Mac Mini: a read-only report on the work board, the agent lanes and
idle sessions, written as one morning page. Stdlib only, python 3.9 ok.

It never writes jobs.json or NEEDS-PHILL.md, never dispatches work, and keeps no probe output:
each lane check is reduced to a fixed state and reason. Spec:
.claude/done/spm/2026-10-30-orchestrator-v1/spec.md

    orchestrator.py              one run (launchd, every 30 min)
    orchestrator.py --deadman    flag the page when no good run landed in 75 min (every 15 min)
"""
import fcntl
import html
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
RUN_DEADLINE_S = 180
DEADMAN_DEADLINE_S = 60
PROBE_TIMEOUT_S = 10
PROBES_TOTAL_S = 30
STALE_AFTER_S = 75 * 60
STALL_HOURS = 6
TOP_N = 5
LOG_KEEP = 2000

PROBES = (
    ("claude", ("claude", "auth", "status")),
    ("codex", ("codex", "login", "status")),
    ("cursor", ("agent", "status")),
    ("pc", ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=1", "pc", "true")),
)
TMUX = ("tmux", "list-sessions", "-F", "#{session_name} #{session_activity}")
ALLOWED_ARGV = {argv for _, argv in PROBES} | {TMUX}

# Lane preference by project, first logged-in lane wins (plan compiled-crunching-bird.md, Lanes).
PROJECT_LANES = {
    "card": ("claude", "cursor"), "cards": ("claude", "cursor"), "business-card": ("claude", "cursor"),
    "carsi": ("pc", "claude"), "restoreassist": ("codex", "claude"), "ra": ("codex", "claude"),
    "unite-group": ("cursor", "claude"), "ug": ("cursor", "claude"), "ccw": ("claude", "codex"),
}
DEFAULT_LANES = ("claude", "codex")


def config():
    vol = os.environ.get("ORCH_VOLUME", "/Volumes/Mini Mini 2T Storage")
    return {
        "board": os.environ.get("ORCH_BOARD", vol + "/ops/jobs.json"),
        "volume": vol,
        "state": os.environ.get("ORCH_STATE_DIR", HOME + "/.local/state/orchestrator"),
        "mirror": os.environ.get("ORCH_MIRROR", vol + "/ops/MORNING.md"),
        "hard_stop": os.environ.get("ORCH_HARD_STOP", HOME + "/.claude/HARD_STOP"),
        "needs_phill": os.environ.get("ORCH_NEEDS_PHILL", vol + "/session-handoffs/NEEDS-PHILL.md"),
        "is_mounted": os.path.ismount,
    }


def now_ts():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------- untrusted text ----------

_MD = re.compile(r"([\\`*_\[\]()#|!~{}])")


def esc(text):
    """Job titles and file lines are untrusted: no HTML, no Markdown structure, one line."""
    return _MD.sub(r"\\\1", html.escape(" ".join(str(text).split()), quote=True))[:160]


# ---------- probes ----------

def run_cmd(argv, timeout):
    """Run one allow-listed command. Returns (exit code or None on timeout, text). Text stays in memory."""
    if tuple(argv) not in ALLOWED_ARGV:
        raise ValueError("command not in the allow-list")
    try:
        p = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, start_new_session=True)
    except FileNotFoundError:
        return 127, ""
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        return None, ""
    return p.returncode, out.decode("utf-8", "replace")


def classify(name, rc, text):
    if rc is None:
        return ("UNREACHABLE" if name == "pc" else "UNKNOWN"), "timeout"
    if rc == 127:
        return "UNKNOWN", "binary_missing"
    t = text.lower()
    if "api key" in t or "api_key" in t or "apikey" in t:
        return "NOT_LOGGED_IN", "api_key_mode"
    if "keychain" in t and "lock" in t:
        return "NOT_LOGGED_IN", "keychain_locked"
    if name == "pc":
        return ("LOGGED_IN", "ssh_ok") if rc == 0 else ("UNREACHABLE", "ssh_failed")
    if "not logged in" in t or "logged out" in t or '"loggedin": false' in t:
        return "NOT_LOGGED_IN", "not_logged_in"
    if rc == 0 and ("logged in" in t or '"loggedin": true' in t):
        return "LOGGED_IN", "logged_in"
    return "UNKNOWN", "unrecognised_output"


def probe_lanes():
    lanes = {}
    pool = ThreadPoolExecutor(max_workers=len(PROBES))
    futures = {pool.submit(run_cmd, argv, PROBE_TIMEOUT_S): name for name, argv in PROBES}
    done, _ = wait(futures, timeout=PROBES_TOTAL_S)
    for fut, name in futures.items():
        if fut in done and fut.exception() is None:
            rc, out = fut.result()
            st, rs = classify(name, rc, out)
        else:
            st, rs = "UNKNOWN", "timeout" if fut not in done else "probe_error"
        lanes[name] = {"state": st, "reason": rs}
    pool.shutdown(wait=False)
    return lanes


def idle_sessions(now):
    rc, out = run_cmd(TMUX, PROBE_TIMEOUT_S)
    if rc != 0:
        return []
    idle = []
    for line in out.splitlines():
        parts = line.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            hours = (now - int(parts[1])) / 3600.0
            if hours > STALL_HOURS:
                idle.append({"session": parts[0], "idle_h": round(hours, 1)})
    return idle


# ---------- board ----------

def load_board(path):
    with open(path) as f:
        d = json.load(f)
    jobs = d.get("jobs") if isinstance(d, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("board has no jobs list")
    return d


def prio(j):
    p = j.get("priority")
    if p is None:
        return 9
    m = re.search(r"\d", str(p))
    if m:
        return int(m.group())
    return {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(str(p).lower(), 8)


def project(j):
    return str(j.get("project") or j.get("repo") or "").strip().lower()


def focus_set(d):
    f = d.get("focus") or []
    if isinstance(f, dict):
        f = f.get("projects") or list(f)
    return {str(x.get("project") if isinstance(x, dict) else x).strip().lower() for x in f}


def rank(d):
    focus = focus_set(d)
    cands = [j for j in d["jobs"]
             if j.get("status") in ("todo", "open") and not j.get("assigned_to") and not j.get("owner")
             and not str(j.get("id", "")).startswith("W-") and not j.get("filler_key")]
    cands.sort(key=lambda j: (0 if project(j) in focus else 1, prio(j), str(j.get("created") or "")))
    return cands


def suggest(jobs, lanes):
    out = []
    for j in jobs[:TOP_N]:
        prefs = PROJECT_LANES.get(project(j), DEFAULT_LANES)
        lane = next((n for n in prefs if lanes.get(n, {}).get("state") == "LOGGED_IN"), None)
        out.append({"id": str(j.get("id", "")), "title": j.get("title") or j.get("name") or "",
                    "lane": lane or "none logged in"})
    return out


def _age_h(j, now):
    for k in ("heartbeat", "updated", "claimed_at", "updated_at"):
        v = j.get(k)
        if not v:
            continue
        try:
            t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (now - t.timestamp()) / 3600.0
    return None


def stalls(d, now):
    out = []
    for j in d["jobs"]:
        if j.get("status") != "doing":
            continue
        age = _age_h(j, now)
        if age is None or age > STALL_HOURS:
            out.append({"id": str(j.get("id", "")), "title": j.get("title") or "",
                        "age_h": None if age is None else round(age, 1)})
    return out


def needs_phill(cfg, d):
    items = []
    try:
        with open(cfg["needs_phill"]) as f:
            items += [ln[2:].strip() for ln in f if ln.startswith("- ")][:15]
    except OSError:
        pass
    if d:
        for j in d["jobs"]:
            if j.get("status") in ("done", "cancelled"):
                continue
            if j.get("needs_phill") or (j.get("status") == "blocked" and "phill" in str(j.get("blocked_on", "")).lower()):
                items.append("%s %s" % (j.get("id", ""), j.get("title", "")))
    return items


# ---------- output ----------

def atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".orch-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _same(a, b):
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def unsafe_paths(cfg):
    """Outputs that would land on a read-only input (same path, symlink or hard link)."""
    outs = [os.path.join(cfg["state"], n) for n in ("MORNING.md", "orchestrator-runs.jsonl", "run.lock")]
    outs.append(cfg["mirror"])
    return [o for o in outs for i in (cfg["board"], cfg["needs_phill"]) if _same(o, i)]


def write_page(cfg, text):
    os.makedirs(cfg["state"], exist_ok=True)
    atomic_write(os.path.join(cfg["state"], "MORNING.md"), text)
    mirror_dir = os.path.dirname(cfg["mirror"])
    if cfg["is_mounted"](cfg["volume"]) and os.path.isdir(mirror_dir):
        atomic_write(cfg["mirror"], text)


def render(row, banner, sugg, stl, idle, needs):
    L = ["Generated %s" % row["ts"], "", "# Morning page", ""]
    if banner:
        L += ["**%s**" % banner, ""]
    L += ["## Lanes", ""]
    for name, v in sorted((row.get("lanes") or {}).items()):
        L.append("- %s: %s (%s)" % (name, v["state"], v["reason"]))
    L += ["", "## Suggested owners", ""]
    if not row["board_read"]:
        L.append("- none: board not read")
    elif not sugg:
        L.append("- No todo jobs")
    for s in sugg:
        L.append("- %s %s -> %s" % (esc(s["id"]), esc(s["title"]), s["lane"]))
    L += ["", "## Stalled and idle", ""]
    for s in stl:
        L.append("- %s %s, %s" % (esc(s["id"]), esc(s["title"]),
                                   "no timestamp" if s["age_h"] is None else "%sh since update" % s["age_h"]))
    for s in idle:
        L.append("- tmux %s idle %sh" % (esc(s["session"]), s["idle_h"]))
    L += ["", "## Needs Phill", ""]
    L += ["- %s" % esc(n) for n in needs] or ["- nothing listed"]
    L += ["", "Queue note for the Board: the ratified queue is mesh_work_claims; this page reads jobs.json.", ""]
    return "\n".join(L)


def append_row(cfg, row):
    os.makedirs(cfg["state"], exist_ok=True)
    path = os.path.join(cfg["state"], "orchestrator-runs.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    with open(path) as f:
        lines = f.readlines()
    if len(lines) > LOG_KEEP:
        atomic_write(path, "".join(lines[-LOG_KEEP:]))


def read_rows(cfg):
    try:
        with open(os.path.join(cfg["state"], "orchestrator-runs.jsonl")) as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except (OSError, ValueError):
        return []


# ---------- run ----------

def _run(cfg, row):
    os.makedirs(cfg["state"], exist_ok=True)
    if os.path.exists(os.path.join(cfg["state"], "ORCHESTRATOR-DISABLED")):
        row.update(ok=False, skipped="disabled")
        write_page(cfg, render(row, "ORCHESTRATOR DISABLED since the marker was written; remove "
                               "ORCHESTRATOR-DISABLED to resume", [], [], [], []))
        return
    if os.path.exists(cfg["hard_stop"]):
        row.update(ok=False, skipped="hard_stop")
        write_page(cfg, render(row, "PAUSED by HARD_STOP", [], [], [], []))
        return
    lock = open(os.path.join(cfg["state"], "run.lock"), "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        row.update(ok=False, skipped="locked")
        return
    try:
        d, banner = None, None
        if not cfg["is_mounted"](cfg["volume"]):
            row["error"] = "volume_not_mounted"
        else:
            try:
                d = load_board(cfg["board"])
            except Exception as e:
                row["error"] = "board_unreadable: %s" % type(e).__name__
        if d is None:
            banner = "BOARD UNREADABLE since %s: %s" % (row["ts"], row["error"])
        row["board_read"] = d is not None
        row["jobs"] = len(d["jobs"]) if d else None
        lanes = probe_lanes()
        row["lanes"] = lanes
        now = time.time()
        sugg = suggest(rank(d), lanes) if d else []
        stl = stalls(d, now) if d else []
        idle = idle_sessions(now)
        row.update(suggestions=len(sugg), stalls=len(stl), idle=len(idle))
        write_page(cfg, render(row, banner, sugg, stl, idle, needs_phill(cfg, d)))
        row["ok"] = d is not None
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def run(cfg):
    start = time.time()
    row = {"ts": now_ts(), "run_id": uuid.uuid4().hex[:12], "ok": False, "skipped": None,
           "board_read": False, "jobs": None, "lanes": {}, "suggestions": 0, "stalls": 0,
           "idle": 0, "error": None}
    if unsafe_paths(cfg):
        row["error"] = "unsafe_paths"
        return row
    try:
        _run(cfg, row)
    except BaseException as e:
        row["ok"] = False
        row["error"] = "deadline" if isinstance(e, Deadline) else "crash: %s" % type(e).__name__
        if not isinstance(e, (Exception, Deadline)):
            raise
    finally:
        row["duration_s"] = round(time.time() - start, 2)
        append_row(cfg, row)
    return row


def deadman(cfg, now=None):
    """Returns OK, PAUSED or STALE; on STALE rewrites the page's first line in both locations."""
    if unsafe_paths(cfg):
        return "UNSAFE"
    now = time.time() if now is None else now
    rows = read_rows(cfg)
    if rows and rows[-1].get("skipped") in ("disabled", "hard_stop"):
        return "PAUSED"
    good = [r for r in rows if r.get("ok")]
    last = None
    if good:
        try:
            last = datetime.fromisoformat(good[-1]["ts"]).timestamp()
        except (KeyError, ValueError):
            last = None
    age = None if last is None else now - last
    if age is not None and age <= STALE_AFTER_S:
        return "OK"
    banner = "ORCHESTRATOR STALE: last good run %s" % (good[-1]["ts"] if good else "never")
    targets = [os.path.join(cfg["state"], "MORNING.md")]
    if cfg["is_mounted"](cfg["volume"]) and os.path.isdir(os.path.dirname(cfg["mirror"])):
        targets.append(cfg["mirror"])
    os.makedirs(cfg["state"], exist_ok=True)
    for t in targets:
        try:
            with open(t) as f:
                body = f.read()
        except OSError:
            body = ""
        if body.startswith("ORCHESTRATOR STALE"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        atomic_write(t, banner + "\n" + body)
    return "STALE"


class Deadline(BaseException):
    """Raised by SIGALRM. Not an OSError or Exception, so no ordinary handler can swallow it."""


def _alarm(signum, frame):
    raise Deadline("deadline")


def main(argv):
    cfg = config()
    bad = unsafe_paths(cfg)
    if bad:
        sys.stderr.write("orchestrator: refusing, output would overwrite an input: %s\n" % ", ".join(bad))
        return 2
    signal.signal(signal.SIGALRM, _alarm)
    if argv[1:2] == ["--deadman"]:
        signal.alarm(DEADMAN_DEADLINE_S)
        try:
            print(deadman(cfg))
        except Deadline:
            print("TIMEOUT: a page write did not finish in %ds" % DEADMAN_DEADLINE_S)
            return 1
        finally:
            signal.alarm(0)
        return 0
    signal.alarm(RUN_DEADLINE_S)
    row = run(cfg)
    signal.alarm(0)
    print("ok" if row["ok"] else "not ok: %s" % (row["skipped"] or row["error"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
