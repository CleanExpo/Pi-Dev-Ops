#!/usr/bin/env python3
"""estate-tidy: the 2-hourly settle, handoff and cleanup pass. SKILL.md beside this file is the contract.

One rule above all: nothing is deleted unless it is safely on GitHub or otherwise backed up.
When unsure, the pass reports and leaves the thing alone.

Stdlib only, Python 3.9 compatible (the MacBook's launchd python is /usr/bin/python3 3.9).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

SSD = "/Volumes/Mini Mini 2T Storage"
MINI_HAND = SSD + "/session-handoffs"
MINI_SYSTEMS = SSD + "/ops-board/systems"
LEDGER_MINI = MINI_HAND + "/IN-FLIGHT.md"
NEEDS_MINI = MINI_HAND + "/NEEDS-PHILL.md"
TASKS_MINI = MINI_HAND + "/TASKS.json"
PC_QUEUE = "/mnt/d/pc-handoff/queue"
PC_STATUS = "/mnt/d/pc-handoff/status"
PC_STATUS_WIN = "D:/pc-handoff/status"
MINI_SSH = "unite-mac-mini"
PC_SSH = "pc"
PC_AGENT = "cloudroom-agent"

HOUR = 3600
PROTECT_WORDS = ("evidence", "report", "receipt", "bundle", "review", "session-handoffs", "pc-bundles", "handoff")
NEVER_KILL = ("claude", "codex", "cursor-agent", "tmux", "ssh", "launchd", "ops_board", "ops-board", "serve.py",
              "pcjob", "systemd", "mosh", "cloudroom", "hermes")
# a node process is a dev server only when one of these is a whole path part (or its stem), or one of the
# pairs is two consecutive argv words; "dev" alone as an argument also counts
DEV_NODE_PARTS = ("vite", "webpack", "webpack-dev-server", "nodemon", "ts-node-dev", "next-server", "storybook")
DEV_NODE_PAIRS = (("next", "dev"), ("astro", "dev"), ("remix", "dev"), ("tsx", "watch"))
# throwaway scripts live here; anything run from these folders is scratch work, not a service
TEMP_ROOTS = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
SCRIPT_RUNNER_RE = re.compile(r"^(python[\d.]*|node|bun|deno)(\.exe)?$", re.I)
# interpreter flags that take the next token as their value, so it is not the script
VALUE_FLAGS = {"-W", "-X", "-Q", "-r", "--require", "--import", "--loader", "--experimental-loader",
               "--env-file", "--inspect-port", "--title", "--max-old-space-size"}
# long-lived bridges that start commands for a remote agent and never reap them (they stay the parent)
REMOTE_BRIDGES = ("desktop-commander",)
BRIDGE_CHILD_MAX_AGE = 12 * HOUR
REGENERABLE_IGNORED = {"node_modules/", ".next/", "dist/", "build/", ".turbo/", "coverage/", "__pycache__/",
                       ".venv/", "venv/", "playwright-report/", "test-results/", ".pytest_cache/", ".ruff_cache/",
                       ".mypy_cache/", "out/", ".cache/", ".vercel/", ".DS_Store", "blob-report/", ".eslintcache",
                       "tsconfig.tsbuildinfo", "next-env.d.ts", ".swc/", "storybook-static/"}
REPO_NAMES = ("Unite-Group", "Synthex", "CARSI", "RestoreAssist", "ra-main", "Pi-Dev-Ops", ".claude",
              "ug-main", "synthex-main")
LEDGER_REPO_ALIASES = {"Unite-Group": ("Unite-Group", "ug-main"), "Synthex": ("Synthex", "synthex-main"),
                       "CARSI": ("CARSI",), "RestoreAssist": ("RestoreAssist", "ra-main"),
                       "Pi-Dev-Ops": ("Pi-Dev-Ops",), "skills-library": (".claude",)}
GH_ORG = "CleanExpo"
RESUME_TAIL = ("After reconciliation, continue the standing goal and every open row you own in IN-FLIGHT.md; "
               "re-arm your /loop or wakeup if you had one. Do not stop to ask.")
NUDGE = "Continue the standing goal from IN-FLIGHT.md."


# --------------------------------------------------------------------------- basics
def ts_local(t=None):
    return dt.datetime.fromtimestamp(t or time.time()).strftime("%Y-%m-%d %H:%M:%S")


def stamp(t=None):
    return dt.datetime.fromtimestamp(t or time.time()).strftime("%Y%m%d-%H%M%S")


def detect_machine():
    try:
        if "microsoft" in Path("/proc/version").read_text().lower():
            return "pc"
    except OSError:
        pass
    return "mini" if "mac-mini" in socket.gethostname().lower() else "macbook"


class Run:
    def __init__(self, args):
        self.args = args
        self.dry = args.dry_run
        self.machine = args.machine or detect_machine()
        self.is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        self.agent = PC_AGENT if (self.machine == "pc" and self.is_root) else None
        self.home = Path("/home/" + PC_AGENT) if self.agent else Path.home()
        default_state = (SSD + "/hot/estate-tidy") if self.machine == "mini" else str(self.home / ".estate-tidy")
        self.state = Path(os.environ.get("ESTATE_TIDY_STATE", default_state))
        self.state.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.report = {
            "schema": "estate-tidy/1", "machine": self.machine, "started": ts_local(self.t0),
            "dry_run": self.dry, "sessions": [], "settle": {}, "ledger": {}, "disk_before": {},
            "disk_after": {}, "worktrees": {"removed": [], "kept": [], "pruned": []}, "processes_killed": [],
            "processes_left": [], "disk_actions": [], "fleet": {}, "board": {}, "lost": [], "stalled": [], "errors": [],
        }
        self.log_lines = []

    def log(self, msg):
        line = "%s [%s%s] %s" % (ts_local(), self.machine, " dry" if self.dry else "", msg)
        self.log_lines.append(line)
        print(line, flush=True)

    def err(self, where, msg):
        self.report["errors"].append({"where": where, "error": str(msg)[:500]})
        self.log("ERROR %s: %s" % (where, msg))


def run(cmd, cwd=None, timeout=120, user=None, env=None, inp=None):
    """Run a command; return (rc, combined output). Never raises."""
    if user:
        cmd = ["runuser", "-u", user, "--", "env", "HOME=/home/" + user, "USER=" + user] + list(cmd)
    try:
        p = subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True, env=env, input=inp)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ss" % timeout
    except (OSError, ValueError) as e:
        return 127, str(e)


def git(R, repo, *a, timeout=180):
    return run(["git", "-C", str(repo)] + list(a), timeout=timeout, user=R.agent)


def protected_name(path):
    low = str(path).lower()
    return any(w in low for w in PROTECT_WORDS)


def df(paths):
    out = {}
    for p in paths:
        try:
            st = os.statvfs(p)
            out[p] = round(st.f_bavail * st.f_frsize / 1e9, 2)
        except OSError:
            pass
    return out


def df_paths(R):
    ps = ["/"]
    if R.machine in ("macbook", "mini"):
        ps = ["/System/Volumes/Data"]
    if R.machine == "mini" and os.path.isdir(SSD):
        ps.append(SSD)
    if R.machine == "pc":
        ps.append("/mnt/d")
    return ps


def backup(R, path, keep=10):
    """Copy path to path.bak-tidy-<ts>; keep only the newest `keep` bak-tidy copies."""
    p = Path(path)
    if not p.exists():
        return None
    b = p.with_name(p.name + ".bak-tidy-" + stamp())
    shutil.copy2(str(p), str(b))
    olds = sorted(p.parent.glob(p.name + ".bak-tidy-*"))
    for o in olds[:-keep]:
        o.unlink()
    return str(b)


def atomic_write(path, text):
    tmp = str(path) + ".tidy-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, str(path))


# --------------------------------------------------------------------------- remote mini files
def mini_read(R, path):
    if R.machine == "mini":
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as e:
            R.err("read " + path, e)
            return None
    if R.machine == "macbook":
        rc, out = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", MINI_SSH, "cat " + shlex.quote(path)],
                      timeout=60)
        if rc == 0:
            return out + "\n"
        R.err("ssh read " + path, out[:200])
        return None
    # PC cannot reach the Mini; the Mini relay pushes a copy of the ledger here.
    local = PC_STATUS + "/" + Path(path).name
    try:
        age = time.time() - os.path.getmtime(local)
        R.report["ledger"]["pc_copy_age_min"] = round(age / 60)
        return Path(local).read_text(encoding="utf-8")
    except OSError as e:
        R.err("read pc copy " + local, e)
        return None


def mini_push_json(R, name, obj):
    data = json.dumps(obj, indent=2, ensure_ascii=False)
    if R.machine == "mini":
        atomic_write(Path(MINI_SYSTEMS) / name, data)
        return "local"
    if R.machine == "macbook":
        dest = MINI_SYSTEMS + "/" + name
        rc, out = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", MINI_SSH,
                       "cat > %s && mv %s %s" % (shlex.quote(dest + ".tmp"), shlex.quote(dest + ".tmp"),
                                                  shlex.quote(dest))], timeout=60, inp=data)
        return "ssh" if rc == 0 else "ssh failed: " + out[:200]
    Path(PC_STATUS).mkdir(parents=True, exist_ok=True)
    atomic_write(Path(PC_STATUS) / name, data)
    return "pc status folder (the Mini relay pulls it)"


# --------------------------------------------------------------------------- process table
def ps_table():
    """pid -> dict(ppid, age_s, user, cmd)."""
    rows = {}
    if sys.platform == "darwin":
        rc, out = run(["ps", "-axo", "pid=,ppid=,etime=,user=,command="], timeout=30)
    else:
        rc, out = run(["ps", "-eo", "pid=,ppid=,etimes=,user=,args="], timeout=30)
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows[pid] = {"ppid": ppid, "age_s": parse_etime(parts[2]), "user": parts[3], "cmd": parts[4]}
    return rows


def parse_etime(s):
    if s.isdigit():
        return int(s)
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    nums = [int(x) for x in s.split(":")]
    while len(nums) < 3:
        nums.insert(0, 0)
    return days * 86400 + nums[0] * 3600 + nums[1] * 60 + nums[2]


def process_cwds(R):
    """Set of cwd paths of every process we can see."""
    cwds = set()
    if sys.platform == "darwin":
        rc, out = run(["lsof", "-a", "-d", "cwd", "-Fn", "-u", os.environ.get("USER", "")], timeout=90)
        for line in out.splitlines():
            if line.startswith("n/"):
                cwds.add(line[1:])
    else:
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                try:
                    cwds.add(os.readlink(str(d / "cwd")))
                except OSError:
                    pass
    return cwds


# --------------------------------------------------------------------------- step 0: sessions
def tmux_bin():
    for b in ("/opt/homebrew/bin/tmux", "/usr/local/bin/tmux", "/usr/bin/tmux"):
        if os.path.exists(b):
            return b
    return None


def tmux_sockets():
    uid = os.getuid()
    names = set()
    for base in ("/private/tmp/tmux-%d" % uid, "/tmp/tmux-%d" % uid):
        if os.path.isdir(base):
            names.update(os.listdir(base))
    return sorted(names)


def find_agent_sessions(R):
    """Live Claude sessions that run inside a known agent tmux pane. Anything else is never touched."""
    tb = tmux_bin()
    sess_dir = R.home / ".claude" / "sessions"
    if not tb or not sess_dir.is_dir():
        return [], "no tmux or no ~/.claude/sessions on this machine"
    procs = ps_table()
    panes = {}  # pane_pid -> (socket, pane_id, session_name)
    for sock in tmux_sockets():
        rc, out = run([tb, "-L", sock, "list-panes", "-a", "-F", "#{pane_pid} #{pane_id} #{session_name}"], timeout=15)
        if rc != 0:
            continue
        for line in out.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[0].isdigit():
                panes[int(parts[0])] = (sock, parts[1], parts[2])
    found = []
    for f in sorted(sess_dir.glob("*.json")):
        try:
            j = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        pid = j.get("pid")
        if not isinstance(pid, int) or pid not in procs or not j.get("tmux"):
            continue
        p, hops = pid, 0
        while p and p not in panes and hops < 8:
            p = procs.get(p, {}).get("ppid")
            hops += 1
        if p not in panes:
            continue
        sock, pane, name = panes[p]
        found.append({"pid": pid, "file": str(f), "socket": sock, "pane": pane, "name": name,
                      "session_id": j.get("sessionId"), "cwd": j.get("cwd")})
    return found, None


def capture(pane, sock, lines=60):
    rc, out = run([tmux_bin(), "-L", sock, "capture-pane", "-p", "-J", "-t", pane, "-S", "-%d" % lines], timeout=15)
    return out if rc == 0 else ""


def session_status(s):
    try:
        j = json.loads(Path(s["file"]).read_text())
    except (OSError, ValueError):
        return None, 0
    return j.get("status"), (j.get("statusUpdatedAt") or 0) / 1000.0


def idle_verdict(s, min_idle=300):
    """Return (idle?, reason). Idle means: status idle for > min_idle s, nothing running, empty prompt."""
    st, since = session_status(s)
    if st != "idle":
        return False, "busy (status %s)" % st
    age = time.time() - since
    if age < min_idle:
        return False, "busy (idle only %ds)" % age
    text = capture(s["pane"], s["socket"], 40)
    if not text:
        return False, "busy (pane unreadable)"
    return idle_from_text(text, age)


def idle_from_text(text, age=0):
    if "esc to interrupt" in text.lower():
        return False, "busy (a tool or turn is running)"
    tail = "\n".join(text.splitlines()[-25:])
    if re.search(r"Do you want|\(y/n\)|❯ 1\.|Press Enter to|waiting for your", tail):
        return False, "busy (a question is on screen)"
    prompts = [l for l in text.splitlines() if l.lstrip().startswith("❯")]
    if not prompts:
        return False, "busy (no empty prompt visible)"
    if prompts[-1].lstrip()[1:].strip():
        return False, "busy (text is typed at the prompt)"
    return True, "idle %d min" % (age // 60)


def send_line(s, text):
    tb = tmux_bin()
    run([tb, "-L", s["socket"], "send-keys", "-t", s["pane"], "-l", text], timeout=15)
    time.sleep(1.5)
    run([tb, "-L", s["socket"], "send-keys", "-t", s["pane"], "Enter"], timeout=15)


def handoff_dir(R):
    d = Path(MINI_HAND + "/tidy-handoffs") if R.machine == "mini" else R.home / "session-handoffs" / "tidy-handoffs"
    d.mkdir(parents=True, exist_ok=True)
    return d


VERDICT_RE = re.compile(r"\b(MATCH|MINOR DRIFT|MATERIAL DRIFT|CANNOT RESUME)\b")
MATCH_PHRASES = ("matched the handoff", "matches the handoff", "resumed cleanly", "state matches")


def classify_resume_text(text):
    m = VERDICT_RE.search(text)
    if m:
        return m.group(1)
    low = text.lower()
    if any(p in low for p in MATCH_PHRASES):
        return "MATCH (stated in words)"
    return None


def resume_evidence(R, s):
    """After /clear the session gets a new id; read its transcript for the reconciliation and handoff use."""
    try:
        j = json.loads(Path(s["file"]).read_text())
    except (OSError, ValueError):
        return {}
    sid = j.get("sessionId")
    out = {"cleared": sid != s.get("session_id"), "new_session_id": sid}
    files = list((R.home / ".claude" / "projects").glob("*/%s.jsonl" % sid))
    if not files:
        return out
    texts, names, n = [], False, 0
    fname = Path(s["handoff"]).name
    for line in files[0].read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        n += 1
        for c in (e.get("message") or {}).get("content") or []:
            if c.get("type") == "text":
                texts.append(c.get("text", ""))
            elif c.get("type") == "tool_use" and fname in json.dumps(c.get("input")):
                names = True
    out.update(assistant_messages=n, names_handoff=names)
    for t in texts:
        v = classify_resume_text(t)
        if v:
            out["verdict"] = v
            out["verdict_text"] = t.strip().splitlines()[0][:200]
            break
    return out


def sessions_step(R):
    mode = R.args.sessions
    if mode == "off":
        R.log("step 0 sessions: off")
        return []
    found, why = find_agent_sessions(R)
    if why:
        R.log("step 0 sessions: none (%s)" % why)
        R.report["sessions"].append({"note": why})
        return []
    live = []
    for s in found:
        if R.args.only_session and s["name"] != R.args.only_session:
            s.update(action="skipped, not selected for this run")
            R.report["sessions"].append(dict(s))
            continue
        idle, reason = idle_verdict(s)
        s["state"] = reason
        if not idle:
            s["action"] = "skipped, busy"
        elif R.dry or mode == "dry":
            s["action"] = "would hand off, /clear, resume"
        else:
            s["action"] = "handoff"
            live.append(s)
        R.log("session %s (%s:%s): %s -> %s" % (s["name"], s["socket"], s["pane"], reason, s["action"]))
        R.report["sessions"].append(s)
    for s in live:
        s["handoff"] = str(handoff_dir(R) / ("handoff-%s-%s-%s.md" % (R.machine, re.sub(r"\W+", "-", s["name"]), stamp())))
        prompt = ("/session-handoff [estate-tidy scheduled handoff] Write the handoff report to exactly %s "
                  "(that path, not docs/session-handoffs). Record every open IN-FLIGHT.md row you own. "
                  "Reply HANDOFF-WRITTEN %s when the file is saved." % (s["handoff"], s["handoff"]))
        send_line(s, prompt)
        s["t_handoff"] = time.time()
        R.log("session %s: handoff requested -> %s" % (s["name"], s["handoff"]))
    # wait for each handoff file plus a return to idle, then /clear and resume
    deadline = time.time() + R.args.handoff_timeout
    pending = list(live)
    while pending and time.time() < deadline:
        time.sleep(20)
        for s in list(pending):
            st, since = session_status(s)
            fp = Path(s["handoff"])
            if fp.exists() and fp.stat().st_size > 200 and st == "idle" and since > s["t_handoff"]:
                ok, why = idle_from_text(capture(s["pane"], s["socket"], 40))
                if not ok:
                    continue
                send_line(s, "/clear")
                time.sleep(8)
                send_line(s, "/resume-from-handoff %s %s" % (s["handoff"], RESUME_TAIL))
                s["t_resume"] = time.time()
                s["action"] = "handoff written, cleared, resume sent"
                R.log("session %s: /clear and resume sent" % s["name"])
                pending.remove(s)
    for s in pending:
        s["action"] = "handoff not finished in time; NOT cleared (never interrupt)"
        R.log("session %s: %s" % (s["name"], s["action"]))
    resumed = [s for s in live if "t_resume" in s]
    # reconciliation verdict, read from the resumed session's own transcript (the screen wording varies)
    deadline = time.time() + R.args.verdict_timeout
    while time.time() < deadline and any("verdict" not in s for s in resumed):
        time.sleep(20)
        for s in resumed:
            if "verdict" not in s:
                ev = resume_evidence(R, s)
                s.update({k: v for k, v in ev.items() if k != "verdict"})
                if ev.get("verdict"):
                    s["verdict"] = ev["verdict"]
                    R.log("session %s: verdict %s, read the handoff %s, cleared %s" %
                          (s["name"], s["verdict"], s.get("names_handoff"), s.get("cleared")))
    for s in resumed:
        if "verdict" not in s:
            st, _since = session_status(s)
            # still working on the reconciliation is progress, not a stall; the continuation check decides
            s["verdict"] = "PENDING (session still busy)" if st == "busy" else "NOT SEEN while idle"
        if s["verdict"] in ("MATERIAL DRIFT", "CANNOT RESUME", "NOT SEEN while idle"):
            R.report["stalled"].append("%s session %s: resume verdict %s (handoff %s)" %
                                       (R.machine, s["name"], s["verdict"], s["handoff"]))
    return resumed


def continuation_check(R, resumed):
    """~10 min after resume: working? if idle, one nudge; 10 min later still idle -> STALLED."""
    for s in resumed:
        wait = s["t_resume"] + 600 - time.time()
        if wait > 0:
            time.sleep(wait)
        st, since = session_status(s)
        if st == "busy" or since > s["t_resume"] + 60:
            s["continue"] = "working (status %s, last change %s)" % (st, ts_local(since))
            if st == "busy":
                continue
        idle, why = idle_verdict(s, min_idle=60)
        if not idle:
            s["continue"] = s.get("continue") or "working (%s)" % why
            continue
        send_line(s, NUDGE)
        s["nudged"] = ts_local()
        R.log("session %s: idle after resume, nudged" % s["name"])
        time.sleep(600)
        idle, why = idle_verdict(s, min_idle=300)
        if idle:
            s["continue"] = "STALLED"
            R.report["stalled"].append("%s session %s: STALLED after resume and one nudge (handoff %s)" %
                                       (R.machine, s["name"], s["handoff"]))
        else:
            s["continue"] = "working after nudge (%s)" % why
        R.log("session %s: continuation %s" % (s["name"], s["continue"]))


# --------------------------------------------------------------------------- ledger
def parse_ledger(text):
    rows = []
    for line in (text or "").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0].lower() == "item" or set(cells[0]) <= set("-: "):
            continue
        item, owner, rb, head, pr, lives, nxt = cells[:7]
        parts = rb.split()
        repo = parts[0] if parts else ""
        branch = parts[1] if len(parts) > 1 and not parts[1].startswith("(") else None
        hm = re.fullmatch(r"[0-9a-f]{7,40}", head)
        prm = re.search(r"(\d{2,6})", pr)
        machine, paths, descr = None, [], []
        ol = owner.lower()
        owner_m = "pc" if ol.startswith("pc") else "mini" if "mini" in ol else None  # an unlabelled path lives with its owner
        pieces = [p.strip() for p in re.split(r",|\s\+\s|;", lives) if p.strip()]
        for idx, piece in enumerate(pieces):
            if idx and re.match(r"^(pc-bundles|reviews|tidy-handoffs)/", piece):
                piece = "~/session-handoffs/" + piece  # relative paths in the ledger live under session-handoffs
            m = None
            for pre, name in (("PC ", "pc"), ("MacBook ", "macbook"), ("Mini ", "mini")):
                if piece.startswith(pre):
                    m, piece = name, piece[len(pre):].strip()
            if m is None and piece.startswith("/Volumes/"):
                m = "mini"
            if m is None and piece.startswith("/mnt/"):
                m = "pc"
            if m is None and piece.startswith("~"):
                m = machine or owner_m or "macbook"  # the ledger is written by the MacBook lead; a bare ~ is the MacBook home
            if m is None and piece.startswith("/"):
                m = machine or owner_m  # e.g. a Mini lead's /private/tmp path: checking it on the MacBook reported false LOST lines
            machine = machine or m
            if piece.startswith(("/", "~")):
                paths.append((m or machine, piece))
            else:
                descr.append(piece)
        if machine is None and owner_m:
            machine = owner_m
        rows.append({"item": item, "owner": owner, "repo": repo, "branch": branch,
                     "head": hm.group(0) if hm else None, "pr": int(prm.group(1)) if prm else None,
                     "machine": machine or "macbook", "paths": paths, "descr": descr, "next": nxt})
    return rows


def repo_checkouts(R):
    """name -> list of local repo paths, deduplicated by git common dir."""
    seen, out = set(), {}
    bases = [R.home]
    if R.machine == "mini":
        bases.append(Path(SSD + "/code"))
    for name in REPO_NAMES:
        for b in bases:
            p = b / name
            if not (p / ".git").exists():
                continue
            rc, common = git(R, p, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=30)
            key = os.path.realpath(common) if rc == 0 else os.path.realpath(str(p))
            if key in seen:
                continue
            seen.add(key)
            out.setdefault(name, []).append(p)
    return out


def ledger_repos(R, repo, checkouts):
    res = []
    for alias in LEDGER_REPO_ALIASES.get(repo, (repo,)):
        res += checkouts.get(alias, [])
    return res


def expand(R, p):
    return str(R.home) + p[1:] if p.startswith("~") else p


def row_bundles(R, row):
    """Bundle files named by the row's paths on this machine (a path, or the bundles inside a folder)."""
    out = []
    for m, p in row["paths"]:
        if m and m != R.machine:
            continue
        pp = expand(R, p)
        if pp.endswith(".bundle") and os.path.isfile(pp):
            out.append(pp)
        elif os.path.isdir(pp):
            out += sorted(str(x) for x in Path(pp).glob("*.bundle"))
    return out


def check_row(R, row, checkouts, attempt_restore):
    checks, lost, restored = [], [], []
    repos = ledger_repos(R, row["repo"], checkouts)
    br = row["branch"]
    branch_missing = False
    if br:
        local = [r for r in repos if git(R, r, "show-ref", "--verify", "--quiet", "refs/heads/" + br)[0] == 0]
        remote_tip = None
        if repos:
            rc, out = git(R, repos[0], "ls-remote", "--heads", "origin", br, timeout=60)
            if rc == 0 and out.strip():
                remote_tip = out.split()[0]
            elif rc != 0:
                checks.append("origin lookup failed: " + out[:120])
        in_bundle = None
        if not local and not remote_tip:
            for cand in row_bundles(R, row):
                rc, out = run(["git", "bundle", "list-heads", cand], timeout=60, user=R.agent)
                if rc == 0 and ("refs/heads/" + br) in out:
                    in_bundle = cand
                    break
        ok = bool(local) or bool(remote_tip) or bool(in_bundle)
        checks.append("branch %s: %s" % (br, "local" if local else ("origin " + remote_tip[:8] if remote_tip else
                                                                     ("bundle " + Path(in_bundle).name if in_bundle else "MISSING"))))
        branch_missing = not ok and bool(repos)
        if not repos:
            checks.append("no local checkout of %s on this machine; branch not checked" % row["repo"])
    if row["head"]:
        h = row["head"]
        found = any(git(R, r, "cat-file", "-e", h + "^{commit}")[0] == 0 for r in repos)
        if not found and br and repos:
            rc, out = git(R, repos[0], "ls-remote", "--heads", "origin", br, timeout=60)
            found = rc == 0 and out.startswith(h)
        if not found:
            for cand in row_bundles(R, row):
                rc, out = run(["git", "bundle", "list-heads", cand], timeout=60, user=R.agent)
                if rc == 0 and h in out:
                    found = True
        checks.append("head %s: %s" % (h, "found" if found else "NOT FOUND"))
        if found and branch_missing:
            checks.append("branch not created yet, but its head commit is preserved (not a loss)")
            branch_missing = False
        if not found and (repos or row["paths"]):
            lost.append("head %s not found in any checkout, on origin or in its bundle" % h)
    if branch_missing:
        lost.append("branch %s missing locally, on origin and in its bundle, and no head commit to fall back on" % br)
    for m, p in row["paths"]:
        if m and m != R.machine:
            checks.append("path %s lives on %s (checked there)" % (p, m))
            continue
        pp = expand(R, p)
        if os.path.exists(pp):
            checks.append("path %s: exists" % p)
            continue
        if attempt_restore and br and repos and not pp.endswith(".bundle") and not R.dry:
            for r in repos:
                if git(R, r, "show-ref", "--verify", "--quiet", "refs/heads/" + br)[0] == 0:
                    rc, out = git(R, r, "worktree", "add", pp, br, timeout=300)
                    if rc == 0:
                        restored.append("worktree %s re-added from branch %s" % (p, br))
                        break
        if restored and os.path.exists(pp):
            checks.append("path %s: RESTORED" % p)
        else:
            checks.append("path %s: MISSING" % p)
            lost.append("path %s is missing" % p)
    if any("worktree" in d.lower() for d in row["descr"]) and br and repos:
        has = False
        for r in repos:
            rc, out = git(R, r, "worktree", "list", "--porcelain")
            has = has or ("branch refs/heads/" + br) in out
        checks.append("worktree for %s: %s" % (br, "found" if has else "none found (branch intact, not a loss)"))
    if row["pr"] and row["repo"] in LEDGER_REPO_ALIASES:
        gh_repo = GH_ORG + "/" + ("skills-library" if row["repo"] == "skills-library" else row["repo"])
        rc, out = run(["gh", "pr", "view", str(row["pr"]), "--repo", gh_repo, "--json", "state", "-q", ".state"],
                      timeout=60, user=R.agent)
        state = out.strip() if rc == 0 else "UNKNOWN (%s)" % out[:80]
        checks.append("PR #%d: %s" % (row["pr"], state))
        if state == "CLOSED":
            lost.append("PR #%d was closed without merging" % row["pr"])
    if not br and not row["paths"] and not row["pr"]:
        checks.append("UNVERIFIABLE: the row names no branch, path or PR")
    return checks, lost, restored


def ledger_check(R, when, text):
    rows = parse_ledger(text)
    checkouts = repo_checkouts(R)
    out = []
    for row in rows:
        if row["machine"] != R.machine:
            out.append({"item": row["item"], "checked_on": row["machine"]})
            continue
        checks, lost, restored = check_row(R, row, checkouts, attempt_restore=(when == "after"))
        out.append({"item": row["item"], "checks": checks, "lost": lost, "restored": restored})
        if when == "after":
            for l in lost:
                R.report["lost"].append("%s: %s (owner %s)" % (row["item"], l, row["owner"]))
    R.report["ledger"][when] = out
    n_here = sum(1 for o in out if "checks" in o)
    n_lost = sum(len(o.get("lost", [])) for o in out)
    R.log("ledger %s: %d rows, %d checked here, %d problems" % (when, len(rows), n_here, n_lost))
    return rows


def ledger_protects(text, path, branch, home):
    if text is None:
        return True  # unreadable ledger: protect everything
    t = text
    p = str(path)
    tilde = "~" + p[len(str(home)):] if p.startswith(str(home)) else None
    if p in t or (tilde and tilde in t):
        return True
    if branch and re.search(r"(?<![\w/.-])%s(?![\w/.-])" % re.escape(branch), t):
        return True
    return False


# --------------------------------------------------------------------------- settle (PC queue)
def pause_flag_text(pid, expires):
    return "pid=%d\nexpires=%d\nwriter=estate-tidy\nset=%s\n" % (pid, expires, ts_local())


def pause_is_stale(text, alive, now):
    """Mirror of the pcqueue check: a PAUSE with a pid is honoured only while that pid lives and before expiry."""
    m = re.search(r"^pid=(\d+)", text or "", re.M)
    if not m:
        return False  # manual pause (no pid): always honoured
    e = re.search(r"^expires=(\d+)", text, re.M)
    return (not alive(int(m.group(1)))) or (not e) or int(e.group(1)) <= now


class Settle:
    def __init__(self, R):
        self.R = R
        self.flag = Path(PC_QUEUE) / "PAUSE"
        self.mine = False

    def __enter__(self):
        R = self.R
        info = R.report["settle"]
        info["seconds"] = R.args.settle_seconds
        if R.args.settle_seconds <= 0:
            info["skipped"] = True
            return self
        if R.machine == "pc" and os.path.isdir(PC_QUEUE):
            if self.flag.exists():
                info["flag"] = "PAUSE already present (someone else's); left as is"
            elif R.dry:
                info["flag"] = "would write %s" % self.flag
            else:
                self.flag.write_text(pause_flag_text(os.getpid(), int(time.time() + R.args.pause_max)))
                self.mine = True
                info["flag"] = "written %s" % ts_local()
            t_flag = time.time()
            if not R.dry:
                time.sleep(R.args.settle_seconds)
            started = self.queue_starts_since(t_flag)
            info["jobs_started_during_settle"] = started
            info["running_jobs"] = run(["systemctl", "list-units", "pcjob-*", "--state=active", "--no-legend",
                                        "--plain"], timeout=20)[1].splitlines()
        elif not R.dry:
            time.sleep(R.args.settle_seconds)
        R.log("settle: %s" % json.dumps(info))
        return self

    def queue_starts_since(self, t):
        try:
            lines = (Path(PC_QUEUE) / "queue.log").read_text().splitlines()
        except OSError:
            return []
        cut = ts_local(t)
        return [l for l in lines if " START " in l and l[:19] >= cut]

    def release(self):
        if self.mine:
            try:
                txt = self.flag.read_text()
                if "pid=%d" % os.getpid() in txt:
                    self.flag.unlink()
            except OSError:
                pass
            self.mine = False
            self.R.report["settle"]["flag_removed"] = ts_local()
            run(["systemctl", "start", "--no-block", "pcqueue.service"], timeout=20)  # next job starts now

    def __exit__(self, *exc):
        self.release()
        return False


# --------------------------------------------------------------------------- worktrees
def worktree_list(R, repo):
    rc, out = git(R, repo, "worktree", "list", "--porcelain")
    wts, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if cur:
                wts.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        cur[k] = v or True
    return wts


def last_activity(R, wt_path):
    """Newest mtime of the worktree's git admin files, read BEFORE any git status touches them."""
    gitfile = Path(wt_path) / ".git"
    try:
        if gitfile.is_file():
            admin = Path(gitfile.read_text().split("gitdir:", 1)[1].strip())
        else:
            admin = gitfile
        ts = [os.path.getmtime(str(admin / n)) for n in ("HEAD", "index", "ORIG_HEAD", "logs/HEAD", "FETCH_HEAD")
              if (admin / n).exists()]
        ts.append(os.path.getmtime(str(wt_path)))
        return max(ts)
    except (OSError, IndexError):
        return time.time()


def unsafe_ignored(R, wt):
    rc, out = git(R, wt, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", timeout=120)
    if rc != 0:
        return ["(could not list ignored files)"]
    bad = []
    for l in out.splitlines():
        base = l.rstrip("/").split("/")[-1] + ("/" if l.endswith("/") else "")
        if base in REGENERABLE_IGNORED or l in REGENERABLE_IGNORED or base.endswith((".pyc", ".log", ".tsbuildinfo")):
            continue
        bad.append(l)
    return bad


def managed_path(path):
    """Worktrees another tool owns, or that sit in a protected folder, are never removed by the tidy."""
    if protected_name(path):
        return "lives in a protected folder (reviews, evidence, handoffs or bundles)"
    if "/.gui-cloudroom/" in path or "/.cloudroom" in path or "/cloudroom/" in path.lower():
        return "managed by the Cloudroom app (thread environment)"
    return None


def decide_worktree(facts):
    """Pure decision. facts keys: locked, dirty, unsafe_ignored, in_ledger, cwd_busy, recent_h, ancestor_main,
    remote_branch_exists, contained_remote, pr_merged, fetch_ok. Returns (remove?, reason)."""
    if not facts.get("fetch_ok"):
        return False, "git fetch failed; cannot prove the work is on GitHub"
    if facts.get("locked"):
        return False, "worktree is locked"
    if facts.get("managed"):
        return False, facts["managed"]
    if facts.get("in_ledger"):
        return False, ("IN-FLIGHT.md unreadable; protecting every worktree" if facts["in_ledger"] == "unreadable"
                       else "named in IN-FLIGHT.md")
    if facts.get("dirty"):
        return False, "tree not clean (%s)" % facts["dirty"]
    if facts.get("unsafe_ignored"):
        return False, "has ignored files that are not rebuildable: %s" % ", ".join(facts["unsafe_ignored"][:3])
    if facts.get("cwd_busy"):
        return False, "a running process has its cwd here"
    if facts.get("recent_h", 99) < 24:
        return False, "used in the last 24 h (%.1f h ago)" % facts["recent_h"]
    if facts.get("ancestor_main"):
        return True, "clean, head already on origin main"
    if facts.get("contained_remote") and (not facts.get("remote_branch_exists") or facts.get("pr_merged")):
        return True, "clean, branch merged or deleted on GitHub, head contained in a remote branch"
    if not facts.get("contained_remote"):
        return False, "head is not on any remote branch (unpushed or squash-merged; kept)"
    return False, "branch still open on GitHub"


def worktrees_step(R, ledger_text):
    cwds = process_cwds(R)
    for name, repos in repo_checkouts(R).items():
        for repo in repos:
            rc, out = git(R, repo, "fetch", "--prune", "--quiet", "origin", timeout=600)
            fetch_ok = rc == 0
            if not fetch_ok:
                R.err("fetch %s" % repo, out[:200])
            rc, dref = git(R, repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
            main_ref = dref.strip() if rc == 0 and dref.strip() else "origin/main"
            wts = worktree_list(R, repo)
            for wt in wts[1:]:  # the first entry is the main checkout itself
                path = wt.get("worktree")
                if not path:
                    continue
                if wt.get("prunable") or not os.path.isdir(path):
                    continue  # handled by prune
                branch = wt["branch"][len("refs/heads/"):] if isinstance(wt.get("branch"), str) else None
                recent_h = (time.time() - last_activity(R, path)) / HOUR
                facts = {"fetch_ok": fetch_ok, "locked": bool(wt.get("locked")), "recent_h": recent_h,
                         "in_ledger": "unreadable" if ledger_text is None else
                         ledger_protects(ledger_text, path, branch, R.home)}
                rp = os.path.realpath(path)
                facts["cwd_busy"] = any(c == rp or c.startswith(rp + "/") or c == path or c.startswith(path + "/")
                                        for c in cwds)
                facts["managed"] = managed_path(path)
                # --no-optional-locks: never refresh the index, or every pass would make the tree look "recent"
                rc, st = git(R, path, "--no-optional-locks", "status", "--porcelain", timeout=180)
                facts["dirty"] = ("%d changed" % len(st.splitlines())) if (rc != 0 or st.strip()) else ""
                if rc != 0:
                    facts["dirty"] = "git status failed: " + st.strip().splitlines()[-1][:120] if st.strip() else "git status failed"
                if not facts["dirty"] and not facts["in_ledger"]:
                    facts["unsafe_ignored"] = unsafe_ignored(R, path)
                head = wt.get("HEAD")
                facts["ancestor_main"] = bool(head) and git(R, repo, "merge-base", "--is-ancestor", head, main_ref)[0] == 0
                if not facts["ancestor_main"] and head:
                    rc, rb = git(R, repo, "branch", "-r", "--contains", head, timeout=120)
                    facts["contained_remote"] = rc == 0 and bool(rb.strip())
                    facts["remote_branch_exists"] = bool(branch) and git(
                        R, repo, "show-ref", "--verify", "--quiet", "refs/remotes/origin/" + branch)[0] == 0
                    if facts["remote_branch_exists"] and facts["contained_remote"]:
                        rc, url = git(R, repo, "remote", "get-url", "origin")
                        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
                        if m:
                            rc, o = run(["gh", "pr", "list", "--repo", m.group(1), "--head", branch, "--state",
                                         "merged", "--json", "number", "-q", "length"], timeout=60, user=R.agent)
                            facts["pr_merged"] = rc == 0 and o.strip() not in ("", "0")
                remove, reason = decide_worktree(facts)
                entry = {"repo": str(repo), "path": path, "branch": branch, "reason": reason}
                if remove and not R.dry:
                    rc, o = git(R, repo, "worktree", "remove", path, timeout=300)  # no --force: git re-checks clean
                    if rc != 0:
                        entry["reason"] = "git refused removal: " + o[:150]
                        R.report["worktrees"]["kept"].append(entry)
                        continue
                (R.report["worktrees"]["removed"] if remove else R.report["worktrees"]["kept"]).append(
                    dict(entry, would=R.dry) if remove else entry)
            rc, o = git(R, repo, "worktree", "prune", "--dry-run", "-v") if R.dry else git(R, repo, "worktree", "prune", "-v")
            if o.strip():
                R.report["worktrees"]["pruned"].append({"repo": str(repo), "detail": o.strip()[:300]})
    R.log("worktrees: %d removed%s, %d kept" % (len(R.report["worktrees"]["removed"]), " (would)" if R.dry else "",
                                                len(R.report["worktrees"]["kept"])))


# --------------------------------------------------------------------------- orphan processes
def throwaway_kind(cmd):
    """A python/node one-off nothing will ever stop: a stdlib preview server, or a script run from a temp
    folder. Returns a short label, or None."""
    toks = cmd.split()
    if not toks or not SCRIPT_RUNNER_RE.match(os.path.basename(toks[0])):
        return None
    if "-m" in toks and toks[toks.index("-m") + 1:toks.index("-m") + 2] == ["http.server"]:
        return "python preview server"
    # fixed roots only: $TMPDIR is not trusted (empty or "/" would match every path; macOS's sits in /var/folders)
    skip = False
    for t in toks[1:]:
        if skip:
            skip = False
            continue
        if t in ("-c", "-e", "-p", "-m", "--eval", "--print"):
            return None  # inline code or a module, not a script file
        if t in VALUE_FLAGS:
            skip = True
            continue
        if t.startswith("-"):
            continue
        return "script run from a temp folder" if t.startswith(TEMP_ROOTS) else None
    return None


LISTENING_KEPT = "temp-folder script listening on a port, left for a person"


def stop_process(pid, wait=None):
    """INT first (Python runs its finally blocks, node exits cleanly), then TERM, then KILL.
    Returns the signals sent. `wait(pid, seconds)` -> True once the process is gone."""
    def gone(p, secs):
        end = time.time() + secs
        while time.time() < end:
            try:
                os.kill(p, 0)
            except OSError:
                return True
            time.sleep(0.2)
        return False
    wait = wait or gone
    sent = []
    for sig, secs in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 0)):
        try:
            os.kill(pid, sig)
        except OSError:
            break
        sent.append(sig.name[3:])
        if secs and wait(pid, secs):
            break
    return " then ".join(sent) or "already gone"


def cmd_parts(cmd):
    """(argv tokens, set of every path component and its extension-less stem), all lower-case."""
    toks = cmd.lower().split()
    parts = set()
    for t in toks:
        for c in t.split("/"):
            if c:
                parts.add(c)
                parts.add(c.split(".")[0] if not c.startswith(".") else c)
    return toks, parts


def has_pair(toks, a, b):
    """`a` (as a program or path basename) immediately followed by the word `b`."""
    return any(os.path.basename(x) == a and y == b for x, y in zip(toks, toks[1:]))


def dev_node(toks, parts):
    return (any(m in parts for m in DEV_NODE_PARTS) or "dev" in toks[1:]
            or any(has_pair(toks, a, b) for a, b in DEV_NODE_PAIRS))


def kill_candidate(info, ports, launchd_pids, pid):
    """Pure decision for one process. Returns (kill?, reason)."""
    cmd = info["cmd"]
    low = cmd.lower()
    first = os.path.basename(cmd.split()[0]) if cmd.split() else ""
    if pid in launchd_pids:
        return False, "launchd job"
    if any(n in first.lower() for n in NEVER_KILL) or any(("/" + n) in low or (" " + n + " ") in low for n in NEVER_KILL):
        return False, "protected program"
    kind = throwaway_kind(cmd)
    # a temp-folder script holding a listening port is serving something; that is not proof it is scratch
    if kind == "script run from a temp folder" and ports:
        return False, LISTENING_KEPT
    if info["ppid"] != 1:
        if info.get("bridge_child") and kind and info["age_s"] >= BRIDGE_CHILD_MAX_AGE:
            return True, "%s left running by %s for over 12 h" % (kind, info["bridge_child"])
        return False, "not orphaned"
    if info["age_s"] < 3 * HOUR:
        return False, "younger than 3 h"
    # Every rule that KILLS matches whole words and path parts, never a substring of the command line:
    # "invite-api" once matched "vite" and an orphaned production service was stopped as a dev server.
    toks, parts = cmd_parts(cmd)
    if has_pair(toks, "next", "dev") or "next-server" in parts:
        return True, "orphaned next dev server"
    if "vitest" in parts:
        return True, "orphaned vitest worker"
    headless = any(t == "--headless" or t.startswith("--headless=") for t in toks)
    chrome = any(p in ("chrome", "chromium") or p.startswith(("chromium-", "chrome-")) for p in parts)
    if (headless and chrome) or "headless_shell" in parts:
        return True, "orphaned headless browser"
    exe = toks[0] if toks else ""
    if "ms-playwright" in parts and ("crashpad" in os.path.basename(exe) or "helper" in os.path.basename(exe)):
        return True, "orphaned Playwright browser helper (its browser is gone)"
    if os.path.basename(exe) in ("node", "node.exe"):
        if ports and min(ports) >= 1024 and dev_node(toks, parts):
            return True, "orphaned node dev server on port %s" % ",".join(map(str, sorted(ports)))
    if kind:
        return True, "orphaned " + kind
    return False, "not a known dev process"


def bridge_ancestor(procs, pid):
    """Name of the remote bridge (REMOTE_BRIDGES) this process descends from, or None."""
    seen = set()
    p = procs.get(pid, {}).get("ppid")
    while p and p not in seen and p in procs:
        seen.add(p)
        low = procs[p]["cmd"].lower()
        for b in REMOTE_BRIDGES:
            if b in low:
                return b
        p = procs[p]["ppid"]
    return None


def listening_ports():
    rc, out = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpn"], timeout=60)
    ports, pid = {}, None
    for line in out.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid:
            m = re.search(r":(\d+)$", line)
            if m:
                ports.setdefault(pid, set()).add(int(m.group(1)))
    return ports


def processes_step(R):
    procs = ps_table()
    me = R.agent or os.environ.get("USER") or ""
    launchd = set()
    if sys.platform == "darwin":
        rc, out = run(["launchctl", "list"], timeout=30)
        for line in out.splitlines():
            f = line.split()
            if f and f[0].isdigit():
                launchd.add(int(f[0]))
    ports = listening_ports() if shutil.which("lsof") else {}
    for pid, info in procs.items():
        u = info["user"].rstrip("+")
        if not u or not me.startswith(u) or pid == os.getpid():
            continue
        if sys.platform != "darwin":
            try:
                cg = Path("/proc/%d/cgroup" % pid).read_text()
                if "pcjob-" in cg or "system.slice" in cg:
                    continue  # pcjob units and systemd services are never orphans
            except OSError:
                continue
        if info["ppid"] != 1:
            info = dict(info, bridge_child=bridge_ancestor(procs, pid))
        kill, reason = kill_candidate(info, ports.get(pid, set()), launchd, pid)
        if not kill:
            if reason == LISTENING_KEPT:
                R.report["processes_left"].append({"pid": pid, "cmd": info["cmd"][:160], "why": reason})
            elif info["ppid"] == 1 and info["age_s"] >= 3 * HOUR and reason == "not a known dev process" and \
                    any(k in info["cmd"].lower() for k in ("node", "chrom", "vitest", "next")) and \
                    not info["cmd"].startswith(("/Applications/", "/System/", "/Library/")):
                R.report["processes_left"].append({"pid": pid, "cmd": info["cmd"][:160], "why": "unsure, left alone"})
            continue
        entry = {"pid": pid, "cmd": info["cmd"][:200], "age_h": round(info["age_s"] / HOUR, 1), "reason": reason}
        if not R.dry:
            entry["signal"] = stop_process(pid)
        else:
            entry["would"] = True
        R.report["processes_killed"].append(entry)
    R.log("processes: %d %s" % (len(R.report["processes_killed"]), "would be killed" if R.dry else "killed"))


# --------------------------------------------------------------------------- disk
def which_native(tool):
    """shutil.which, but never a Windows binary reached through WSL interop (/mnt/c/...)."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d.startswith("/mnt/"):
            continue
        p = os.path.join(d, tool)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def disk_step(R):
    acts = R.report["disk_actions"]

    def act(name, cmd, timeout=900, user=None):
        if R.dry:
            acts.append({"step": name, "would_run": " ".join(cmd)})
            return
        rc, out = run(cmd, timeout=timeout, user=user)
        acts.append({"step": name, "rc": rc, "out": out[-300:]})
        if rc != 0:
            R.err(name, out[-200:])

    docker = which_native("docker") or ("/usr/local/bin/docker" if os.path.exists("/usr/local/bin/docker") else None)
    if docker and run([docker, "system", "df"], timeout=30)[0] == 0:
        act("docker volume prune (dangling, no --all)", [docker, "volume", "prune", "-f"])
        act("docker image prune (dangling)", [docker, "image", "prune", "-f"])
    else:
        acts.append({"step": "docker", "skipped": "docker not installed or not running"})
    npm = which_native("npm")
    if npm:
        act("npm cache verify", [npm, "cache", "verify"], user=R.agent)
    pnpm = which_native("pnpm")
    installing = [i["cmd"][:80] for i in ps_table().values()
                  if re.search(r"\b(pnpm|npm|yarn)(\.cjs)?\s+(install|i|ci|add)\b", i["cmd"])]
    if pnpm and installing:
        acts.append({"step": "pnpm store prune", "skipped": "a package install is running: %s" % installing[0]})
    elif pnpm:
        # a large store takes over 15 min to prune on the Mini SSD: once a day, with an hour's room
        stampf = R.state / "pnpm-prune-ok"
        age = time.time() - stampf.stat().st_mtime if stampf.exists() else 1e9
        if age < 86400:
            acts.append({"step": "pnpm store prune", "skipped": "ran %.1f h ago (daily)" % (age / HOUR)})
        else:
            before = len(acts)
            act("pnpm store prune", [pnpm, "store", "prune"], timeout=3600, user=R.agent)
            if not R.dry and acts[before].get("rc") == 0:
                stampf.write_text(ts_local())
    playwright_gc(R)
    tmp_gc(R)


def playwright_gc(R):
    acts = R.report["disk_actions"]
    cands = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), str(R.home / "Library/Caches/ms-playwright"),
             str(R.home / ".cache/ms-playwright"), SSD + "/hot/caches/ms-playwright", SSD + "/hot/caches/playwright"]
    for root in [c for c in cands if c and os.path.isdir(c)]:
        root = Path(root)
        links = root / ".links"
        if not links.is_dir():
            acts.append({"step": "playwright %s" % root, "skipped": "no .links registry; unsure which versions are used"})
            continue
        used = set()
        live = 0
        for lf in links.iterdir():
            try:
                pkg = Path(lf.read_text().strip())
                bj = json.loads((pkg / "browsers.json").read_text())
                live += 1
                for b in bj.get("browsers", []):
                    used.add("%s-%s" % (b["name"].replace("-", "_"), b["revision"]))
                    for k, v in (b.get("revisionOverrides") or {}).items():
                        used.add("%s-%s" % (b["name"].replace("-", "_"), v))
            except (OSError, ValueError, KeyError):
                continue
        # also every checkout's installed playwright-core
        for bj in list(R.home.glob("*/node_modules/playwright-core/browsers.json")) + \
                list(R.home.glob("*/node_modules/.pnpm/playwright-core@*/node_modules/playwright-core/browsers.json")):
            try:
                for b in json.loads(bj.read_text()).get("browsers", []):
                    used.add("%s-%s" % (b["name"].replace("-", "_"), b["revision"]))
            except (OSError, ValueError, KeyError):
                pass
        if live == 0:
            acts.append({"step": "playwright %s" % root, "skipped": "no live installation links; unsure, left alone"})
            continue
        for d in root.iterdir():
            if not d.is_dir() or d.name.startswith(".") or not re.fullmatch(r"[a-z_]+-\d+", d.name):
                continue
            if d.name in used or time.time() - d.stat().st_mtime < 7 * 86400:
                continue
            if R.dry:
                acts.append({"step": "playwright old browser", "would_delete": str(d)})
            else:
                shutil.rmtree(str(d), ignore_errors=True)
                acts.append({"step": "playwright old browser", "deleted": str(d)})


def tmp_roots(R):
    roots = []
    for g in ("/private/tmp", "/tmp"):
        if os.path.isdir(g):
            for d in sorted(Path(g).glob("claude-*")):
                roots.append((d, 48 * HOUR))  # scratchpads: never younger than 48 h
            break
    if sys.platform == "darwin":
        rc, t = run(["getconf", "DARWIN_USER_TEMP_DIR"], timeout=10)
        if rc == 0 and t.strip():
            roots.append((Path(t.strip()), 24 * HOUR))
    else:
        roots.append((Path("/tmp"), 24 * HOUR))
    if R.machine == "mini" and os.path.isdir(SSD + "/hot/tmp"):
        roots.append((Path(SSD + "/hot/tmp"), 24 * HOUR))
    return roots


SKIP_TMP_PREFIX = ("com.apple.", "systemd-private-", "snap-private-tmp", "tmux-", ".X11-unix", ".ICE-unix", "ssh-",
                   "claude-", "cc-socks", ".font-unix", "pcjob", "estate-tidy")


def tmp_gc(R):
    count, freed = 0, 0
    sample, gitdirs = [], []
    now = time.time()
    linked = []
    for root, max_age in tmp_roots(R):
        top_is_claude = root.name.startswith("claude-")
        # os.walk follows the ROOT even with followlinks=False, so a symlinked root would sweep its target
        if os.path.islink(str(root)) or not os.path.isdir(str(root)):
            if os.path.islink(str(root)):
                linked.append(str(root))
            continue
        real_root = os.path.realpath(str(root))
        for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
            real = os.path.realpath(dirpath)
            if real != real_root and not real.startswith(real_root + os.sep):
                dirnames[:] = []
                continue
            rel = os.path.relpath(dirpath, str(root))
            first = rel.split(os.sep)[0] if rel != "." else ""
            if not top_is_claude and rel == ".":
                # hidden or bundle-id folders belong to running apps (Codex, browsers); folders touched in the
                # last 24 h are in use. Both are left alone.
                dirnames[:] = [d for d in dirnames if not d.startswith(SKIP_TMP_PREFIX) and not d.startswith(".")
                               and not re.match(r"^[a-z]{2,}\.[\w-]+\.", d)
                               and now - os.lstat(os.path.join(dirpath, d)).st_mtime >= max_age]
            dirnames[:] = [d for d in dirnames if not protected_name(d)]
            if ".git" in dirnames or ".git" in filenames:
                gitdirs.append(dirpath)  # a checkout in temp may hold uncommitted work: never touched
                dirnames[:] = []
                continue
            if first and not top_is_claude and first.startswith(SKIP_TMP_PREFIX):
                continue
            for fn in filenames:
                if protected_name(fn) or (rel == "." and not top_is_claude and fn.startswith(SKIP_TMP_PREFIX)):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                import stat as _s
                if not _s.S_ISREG(st.st_mode) or now - st.st_mtime < max_age:
                    continue
                if R.agent is None and st.st_uid != os.getuid():
                    continue
                count += 1
                freed += st.st_size
                if len(sample) < 5:
                    sample.append(fp)
                if not R.dry:
                    try:
                        os.unlink(fp)
                    except OSError:
                        count -= 1
                        freed -= st.st_size
    R.report["disk_actions"].append({"step": "temp files older than 24 h (48 h for claude scratchpads)",
                                     ("would_delete" if R.dry else "deleted"): count,
                                     "bytes": freed, "sample": sample,
                                     "git_checkouts_left_alone": len(gitdirs), "git_checkouts_sample": gitdirs[:5],
                                     "symlinked_roots_skipped": linked})


# --------------------------------------------------------------------------- board hygiene (Mini)
def gh_pr_state(url_or_repo, num=None, cache={}):
    key = (url_or_repo, num)
    if key not in cache:
        cmd = ["gh", "pr", "view", url_or_repo, "--json", "state", "-q", ".state"] if num is None else \
            ["gh", "pr", "view", str(num), "--repo", url_or_repo, "--json", "state", "-q", ".state"]
        rc, out = run(cmd, timeout=60)
        cache[key] = out.strip() if rc == 0 else None
    return cache[key]


PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def board_step(R):
    b = R.report["board"]
    try:
        data = json.loads(Path(TASKS_MINI).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        R.err("TASKS.json", e)
        data = None
    marked = []
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        for t in data["tasks"]:
            if t.get("status") == "done":
                continue
            urls = sorted(set(PR_URL.findall((t.get("title") or "") + " " + (t.get("note") or ""))))
            if not urls:
                continue
            states = [gh_pr_state(u) for u in urls]
            if all(s == "MERGED" for s in states) and t.get("status") in ("waiting", "blocked"):
                b.setdefault("tasks_left_unsure", []).append(
                    "%s: PR merged but the row is %s on something else; left for the lead" % (t.get("title"), t.get("status")))
            elif all(s == "MERGED" for s in states):
                marked.append(t.get("title"))
                if not R.dry:
                    t["status"] = "done"
                    t["note"] = (t.get("note") or "") + " [estate-tidy %s: PR merged, marked done]" % ts_local()[:16]
        if marked and not R.dry:
            b["tasks_backup"] = backup(R, TASKS_MINI)
            atomic_write(TASKS_MINI, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    b["tasks_marked_done"] = marked
    try:
        lines = Path(NEEDS_MINI).read_text(encoding="utf-8").splitlines(True)
    except OSError as e:
        R.err("NEEDS-PHILL.md", e)
        return
    keep, pruned, unsure = [], [], []
    for l in lines:
        urls = PR_URL.findall(l)
        if l.startswith("- ") and urls and not re.match(r"- (LOST|STALLED)", l):
            states = [gh_pr_state(u) for u in urls]
            if all(s in ("MERGED", "CLOSED") for s in states):
                pruned.append(l.strip()[:160])
                continue
        elif l.startswith("- ") and re.search(r"#\d{3,5}", l):
            unsure.append(l.strip()[:100])
        keep.append(l)
    b["needs_pruned"] = pruned
    b["needs_left_unsure"] = "%d lines name a PR by number only; left alone (repo not stated)" % len(unsure)
    if pruned and not R.dry:
        b["needs_backup"] = backup(R, NEEDS_MINI)
        atomic_write(NEEDS_MINI, "".join(keep))


def propagate_alerts(R, extra_reports=()):
    """Write LOST and STALLED lines from every tidy-*.json (and this run) to the top of NEEDS-PHILL.md,
    and remove the ones a machine's latest report no longer carries.

    26/10/2026: four false LOST lines (Mini paths checked on the MacBook) stayed on Phill's list
    after the 18:20 MacBook report came back clean, because lines were only ever added. A line
    is removed only when that machine's current report was read; an unreadable report clears
    nothing, and STALLED lines (no machine named) clear only when every report was read."""
    if R.machine != "mini":
        return []
    items, seen, all_read = [], set(), True
    for f in sorted(Path(MINI_SYSTEMS).glob("tidy-*.json")):
        if f.name.endswith("-dryrun.json") or (extra_reports and f.name == "tidy-%s.json" % R.machine):
            continue  # dry runs raise nothing; this machine's previous report is superseded by this run
        try:
            j = json.loads(f.read_text())
        except (OSError, ValueError):
            all_read = False
            continue
        seen.add(j.get("machine"))
        for l in j.get("lost", []):
            items.append("LOST (estate-tidy, %s): %s" % (j.get("machine"), l))
        for s in j.get("stalled", []):
            items.append("STALLED (estate-tidy): %s" % s)
    for rep in extra_reports:
        seen.add(rep.get("machine"))
        for l in rep.get("lost", []):
            items.append("LOST (estate-tidy, %s): %s" % (rep.get("machine"), l))
        for s in rep.get("stalled", []):
            items.append("STALLED (estate-tidy): %s" % s)
    try:
        text = Path(NEEDS_MINI).read_text(encoding="utf-8")
    except OSError as e:
        R.err("NEEDS-PHILL.md", e)
        return []
    current = set(items)
    lines, cleared = [], []
    for l in text.splitlines(True):
        m = re.match(r"- (LOST \(estate-tidy, ([^)]+)\): .*|STALLED \(estate-tidy\): .*)$", l.rstrip("\n"))
        if m and m.group(1) not in current and (m.group(2) in seen if m.group(2) else all_read):
            cleared.append(m.group(1)[:160])
            continue
        lines.append(l)
    R.report["alerts_cleared"] = cleared
    new = [i for i in dict.fromkeys(items) if i not in text]
    if (new or cleared) and not R.dry:
        backup(R, NEEDS_MINI)
        head = 1 if lines and lines[0].startswith("#") else 0
        lines[head:head] = ["- %s\n" % i for i in new]
        atomic_write(NEEDS_MINI, "".join(lines))
    return new


def relay(R):
    """Mini only, every 5 min: pull the PC's tidy report, push the ledger to the PC, raise LOST/STALLED lines."""
    out = {}
    rc, txt = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", PC_SSH,
                   "type D:\\pc-handoff\\status\\tidy-pc.json"], timeout=40)
    if rc == 0:
        try:
            json.loads(txt)
            atomic_write(Path(MINI_SYSTEMS) / "tidy-pc.json", txt)
            out["pull"] = "ok"
        except ValueError:
            out["pull"] = "not valid json yet"
    else:
        out["pull"] = "failed: " + txt[:120]
    rc, o = run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", LEDGER_MINI,
                 "%s:%s/IN-FLIGHT.md" % (PC_SSH, PC_STATUS_WIN)], timeout=40)
    out["ledger_push"] = "ok" if rc == 0 else "failed: " + o[:120]
    out["raised"] = propagate_alerts(R)
    print(json.dumps(out))
    return 0


# --------------------------------------------------------------------------- main
# --------------------------------------------------------------------------- fleet versions
FLEET_SHARE = ".local/share/fleet-sync/fleet-sync"   # installed on every machine by fleet-sync --apply


def fleet_state(rc, out):
    """Turn `fleet-sync --check --self --json` into a report block. Anything unreadable is UNPROVEN, never GREEN."""
    try:
        d = json.loads(out[out.index("{"):])
    except (ValueError, TypeError):
        return {"state": "UNPROVEN", "exit": rc, "drift": [], "why": "fleet-sync gave no JSON: " + (out or "")[-200:]}
    if rc != d.get("exit") or rc not in (0, 1, 2):
        return {"state": "UNPROVEN", "exit": rc, "drift": [], "why": "exit code %s disagrees with the JSON (%s)" % (rc, d.get("exit"))}
    return {"state": {0: "GREEN", 1: "DRIFT", 2: "BLOCKED"}[rc], "exit": rc, "drift": d.get("drift", []),
            "manifest_sha": d.get("manifest_sha"), "checked": ts_local()}


def fleet_step(R):
    """Read-only. Reports version drift against fleet-versions.json; it never upgrades anything.
    Upgrades happen together, on purpose, with `fleet-sync --apply`."""
    script = R.home / FLEET_SHARE
    if not script.exists():
        R.report["fleet"] = {"state": "UNPROVEN", "why": "fleet-sync is not installed at %s" % script}
        R.err("fleet", "fleet-sync not installed at %s; run fleet-sync --apply" % script)
        return
    rc, out = run([sys.executable, str(script), "--check", "--self", "--json"], timeout=300)
    f = R.report["fleet"] = fleet_state(rc, out)
    if f["state"] == "GREEN":
        R.log("fleet: GREEN, every tool matches fleet-versions.json")
    elif f["state"] == "UNPROVEN":
        R.err("fleet", f["why"])
    else:
        R.log("fleet: %s, %d item(s): %s" % (f["state"], len(f["drift"]), "; ".join(f["drift"][:6])))



def acquire_lock(R):
    f = open(str(R.state / "lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another estate-tidy pass is running; exiting")
        sys.exit(0)
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description="estate-tidy pass")
    ap.add_argument("--dry-run", action="store_true", help="plan only: nothing is deleted, paused, killed or sent")
    ap.add_argument("--machine", choices=["macbook", "mini", "pc"])
    ap.add_argument("--sessions", choices=["off", "dry", "on"], default="off")
    ap.add_argument("--only-session", help="act on this tmux session name only")
    ap.add_argument("--settle-seconds", type=int, default=300)
    ap.add_argument("--pause-max", type=int, default=3600, help="PAUSE flag expiry (crash safety)")
    ap.add_argument("--handoff-timeout", type=int, default=2400)
    ap.add_argument("--verdict-timeout", type=int, default=1800)
    ap.add_argument("--skip", default="", help="comma list: sessions,ledger,settle,worktrees,processes,disk,fleet,board")
    ap.add_argument("--relay", action="store_true", help="Mini: pull PC report, push ledger, raise alerts")
    ap.add_argument("--ledger-only", action="store_true", help="snapshot and check the ledger, nothing else")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    R = Run(a)
    if a.relay:
        return relay(R)
    lockf = acquire_lock(R)
    skip = set(x for x in a.skip.split(",") if x)
    settle = None

    def on_signal(sig, _frm):
        R.err("signal", "received %d; releasing the pause flag and stopping" % sig)
        if settle:
            settle.release()
        finish(R)
        sys.exit(1)

    for sg in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sg, on_signal)
    R.report["disk_before"] = df(df_paths(R))
    resumed = []
    try:
        ledger_text = mini_read(R, LEDGER_MINI)
        if ledger_text is not None:
            snap = R.state / "ledger-snapshots"
            snap.mkdir(exist_ok=True)
            (snap / ("IN-FLIGHT-%s.md" % stamp())).write_text(ledger_text)
            for o in sorted(snap.glob("IN-FLIGHT-*.md"))[:-24]:
                o.unlink()
            R.report["ledger"]["snapshot"] = str(snap)
        else:
            R.report["ledger"]["snapshot"] = "UNREADABLE: no worktree will be removed this pass"
        if "ledger" not in skip:
            ledger_check(R, "before", ledger_text)
        if a.ledger_only:
            ledger_check(R, "after", ledger_text)
            return finish(R)
        if "sessions" not in skip:
            resumed = sessions_step(R)
        settle = Settle(R)
        if "settle" in skip:
            a.settle_seconds = 0
        with settle:
            for name, fn in (("worktrees", lambda: worktrees_step(R, ledger_text)), ("processes", lambda: processes_step(R)),
                             ("disk", lambda: disk_step(R)),
                             ("fleet", lambda: fleet_step(R)),
                             ("board", lambda: board_step(R) if R.machine == "mini" else None)):
                if name in skip:
                    continue
                try:
                    fn()
                except Exception as e:  # noqa: BLE001 - one step failing must not stop the others
                    R.err(name, "%s: %s" % (type(e).__name__, e))
        if "ledger" not in skip:
            ledger_check(R, "after", mini_read(R, LEDGER_MINI) or ledger_text)
        if resumed and not R.dry:
            continuation_check(R, resumed)
    except Exception as e:  # noqa: BLE001
        R.err("pass", "%s: %s" % (type(e).__name__, e))
    finally:
        if settle:
            settle.release()
    return finish(R)


def finish(R):
    R.report["disk_after"] = df(df_paths(R))
    R.report["finished"] = ts_local()
    R.report["minutes"] = round((time.time() - R.t0) / 60, 1)
    name = "tidy-%s%s.json" % (R.machine, "-dryrun" if R.dry else "")
    if R.machine == "mini" and not R.dry:
        R.report["raised_to_needs_phill"] = propagate_alerts(R, [R.report])
    R.report["delivered"] = mini_push_json(R, name, R.report)
    (R.state / name).write_text(json.dumps(R.report, indent=2, ensure_ascii=False))
    with open(str(R.state / "runs.jsonl"), "a") as f:
        f.write(json.dumps({"t": R.report["started"], "dry": R.dry, "errors": len(R.report["errors"]),
                            "lost": len(R.report["lost"]), "removed": len(R.report["worktrees"]["removed"])}) + "\n")
    with open(str(R.state / "tidy.log"), "a") as f:
        f.write("\n".join(R.log_lines) + "\n")
    R.log("done in %s min; report %s (%s)" % (R.report["minutes"], name, R.report["delivered"]))
    return 0 if not R.report["errors"] else 2


# --------------------------------------------------------------------------- self-test
def selftest():
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    check("protect evidence", protected_name("/tmp/x/review-evidence.json"))
    check("protect bundle", protected_name("/tmp/a/legal2-final.bundle"))
    check("protect handoffs", protected_name("/x/session-handoffs/y.md"))
    check("plain tmp not protected", not protected_name("/tmp/claude-501/abc/tmp123.txt"))
    base = {"ppid": 1, "age_s": 4 * HOUR, "user": "u"}
    check("kill orphan next dev", kill_candidate(dict(base, cmd="node /x/node_modules/.bin/next dev -p 3001"), {3001}, set(), 9)[0])
    check("kill orphan vitest", kill_candidate(dict(base, cmd="node /x/vitest/dist/workers/forks.js"), set(), set(), 9)[0])
    check("kill headless chrome", kill_candidate(dict(base, cmd="/x/ms-playwright/chromium-1140/chrome --headless"), set(), set(), 9)[0])
    check("never kill claude", not kill_candidate(dict(base, cmd="claude --permission-mode auto vitest next dev"), {3000}, set(), 9)[0])
    check("never kill codex", not kill_candidate(dict(base, cmd="/usr/local/bin/codex exec vitest next dev"), {3000}, set(), 9)[0])
    check("never kill tmux", not kill_candidate(dict(base, cmd="tmux new -d -s lead vitest next dev"), {3000}, set(), 9)[0])
    check("never kill launchd job", not kill_candidate(dict(base, cmd="node /x/next dev"), {3000}, {9}, 9)[0])
    check("headful playwright main kept", not kill_candidate(dict(base, cmd="/x/ms-playwright/chromium-1/Chrome --user-data-dir=/y"), set(), set(), 9)[0])
    check("never kill young", not kill_candidate(dict(base, age_s=HOUR, cmd="node /x/next dev"), set(), set(), 9)[0])
    check("never kill non-orphan", not kill_candidate(dict(base, ppid=55, cmd="node /x/next dev"), set(), set(), 9)[0])
    check("node server w/o dev marker kept", not kill_candidate(dict(base, cmd="node server.js"), {8790}, set(), 9)[0])
    check("ops board kept", not kill_candidate(dict(base, cmd="node /x/ops-board/serve.js next dev"), {8787}, set(), 9)[0])
    py = "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python"
    check("kill orphan http.server", kill_candidate(dict(base, cmd=py + " -m http.server 8878 --bind 127.0.0.1 --directory /tmp/l"), {8878}, set(), 9)[0])
    check("kill orphan tmp python script", kill_candidate(dict(base, cmd=py + " -u /tmp/lanes/run/refresh.py"), set(), set(), 9)[0])
    check("kill orphan tmp node script", kill_candidate(dict(base, cmd="node /tmp/lanes/run38/qa.cjs"), set(), set(), 9)[0])
    check("kill orphan private/tmp script", kill_candidate(dict(base, cmd="python3 /private/tmp/x/server.py"), set(), set(), 9)[0])
    check("young tmp script kept", not kill_candidate(dict(base, age_s=HOUR, cmd="node /tmp/lanes/qa.cjs"), set(), set(), 9)[0])
    check("home python service kept", not kill_candidate(dict(base, cmd="python3 -u /Users/u/.local/share/nexus-mesh/heartbeat.py --loop"), set(), set(), 9)[0])
    check("inline -c probe kept", not kill_candidate(dict(base, cmd="python3 -I -c import os /tmp/hung-vol-x/vol"), set(), set(), 9)[0])
    old_tmpdir = os.environ.get("TMPDIR")
    try:
        for bad in ("", "/", "/Users/u"):
            os.environ["TMPDIR"] = bad
            check("TMPDIR=%r does not widen temp" % bad,
                  not kill_candidate(dict(base, cmd="node /Users/u/app/server.js"), set(), set(), 9)[0])
    finally:
        if old_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old_tmpdir
    check("nodemon is not a bare runner", throwaway_kind("/usr/local/bin/nodemon /tmp/x.js") is None)
    check("node -r preload judged on script", throwaway_kind("node -r /tmp/pre.js /Users/u/server.js") is None)
    check("python -W value skipped", throwaway_kind("python3 -W ignore /tmp/x.py") == "script run from a temp folder")
    check("python -X value skipped", throwaway_kind(py + " -X dev -u /tmp/x.py") == "script run from a temp folder")
    check("python3.11 runner matched", throwaway_kind("/opt/bin/python3.11 /tmp/x.py") == "script run from a temp folder")
    check("-m last token safe", throwaway_kind("python3 -m") is None)
    dc = dict(base, ppid=55, age_s=13 * HOUR, bridge_child="desktop-commander")
    check("kill bridge child tmp script >12h", kill_candidate(dict(dc, cmd="node /tmp/lanes/test_run22.cjs"), set(), set(), 9)[0])
    check("kill bridge child http.server >12h", kill_candidate(dict(dc, cmd="python3 -m http.server 8877"), {8877}, set(), 9)[0])
    check("bridge child <12h kept", not kill_candidate(dict(dc, age_s=11 * HOUR, cmd="node /tmp/lanes/t.cjs"), set(), set(), 9)[0])
    check("bridge child non-throwaway kept", not kill_candidate(dict(dc, cmd="node /Users/u/app/server.js"), set(), set(), 9)[0])
    check("plain child tmp script kept", not kill_candidate(dict(dc, bridge_child=None, cmd="node /tmp/lanes/t.cjs"), set(), set(), 9)[0])
    try:
        tree = {10: {"ppid": 1, "cmd": "node /x/.bin/desktop-commander remote"}, 11: {"ppid": 10, "cmd": "zsh -l -c node x"},
                12: {"ppid": 11, "cmd": "node /tmp/a.cjs"}, 20: {"ppid": 1, "cmd": "zsh"}, 21: {"ppid": 20, "cmd": "node /tmp/b.cjs"}}
        check("bridge ancestor found", bridge_ancestor(tree, 12) == "desktop-commander")
        check("no bridge ancestor", bridge_ancestor(tree, 21) is None)
    except NameError:
        check("bridge_ancestor exists", False)
    ok = {"fetch_ok": True, "recent_h": 48, "ancestor_main": True}
    check("remove merged clean", decide_worktree(ok)[0])
    check("keep dirty", not decide_worktree(dict(ok, dirty="1 changed"))[0])
    check("keep ledger", not decide_worktree(dict(ok, in_ledger=True))[0])
    check("keep cwd busy", not decide_worktree(dict(ok, cwd_busy=True))[0])
    check("keep recent", not decide_worktree(dict(ok, recent_h=2))[0])
    check("keep locked", not decide_worktree(dict(ok, locked=True))[0])
    check("keep reviews folder", not decide_worktree(dict(ok, managed=managed_path("/u/session-handoffs/reviews/x/rcopy")))[0])
    check("keep cloudroom", not decide_worktree(dict(ok, managed=managed_path("/u/.gui-cloudroom/plugins/w/thr_1/x")))[0])
    check("plain wt not managed", managed_path("/u/.claude-worktrees/ug-x") is None)
    check("keep env file", not decide_worktree(dict(ok, unsafe_ignored=[".env.local"]))[0])
    check("keep no fetch", not decide_worktree(dict(ok, fetch_ok=False))[0])
    nm = {"fetch_ok": True, "recent_h": 48, "ancestor_main": False}
    check("keep unpushed", not decide_worktree(dict(nm, contained_remote=False))[0])
    check("keep open branch", not decide_worktree(dict(nm, contained_remote=True, remote_branch_exists=True))[0])
    check("remove deleted branch", decide_worktree(dict(nm, contained_remote=True, remote_branch_exists=False))[0])
    check("remove merged pr", decide_worktree(dict(nm, contained_remote=True, remote_branch_exists=True, pr_merged=True))[0])
    led = ("| Item | Owner | Repo / branch | Head | PR | Lives at | Next step |\n|---|---|---|---|---|---|---|\n"
           "| A | lead | Unite-Group fix/a-b | 9ee61faf | 1257 | MacBook ~/.claude-worktrees/ug-a | x |\n"
           "| B | helper | Synthex (helper branch) | (helper) | - | MacBook worktree | y |\n"
           "| C | PC job | Unite-Group fix/legal | (running) | - | PC ~/wt-legal, /mnt/d/pc-handoff/legal | z |\n")
    led += "| D | helper | Unite-Group fix/d | 7f772d5a | - | MacBook ~/.claude-worktrees/ug-d + pc-bundles/d/d.bundle | n |\n"
    rows = parse_ledger(led)
    check("ledger plus split", [p for _m, p in rows[3]["paths"]] == ["~/.claude-worktrees/ug-d", "~/session-handoffs/pc-bundles/d/d.bundle"])
    rows = rows[:3]
    check("ledger rows", len(rows) == 3)
    check("ledger branch", rows[0]["branch"] == "fix/a-b" and rows[0]["head"] == "9ee61faf" and rows[0]["pr"] == 1257)
    check("ledger macbook path", rows[0]["machine"] == "macbook" and rows[0]["paths"][0][1] == "~/.claude-worktrees/ug-a")
    check("ledger helper branch none", rows[1]["branch"] is None and rows[1]["head"] is None)
    check("ledger pc", rows[2]["machine"] == "pc" and len(rows[2]["paths"]) == 2)
    check("ledger protects path", ledger_protects(led, "/Users/u/.claude-worktrees/ug-a", None, "/Users/u"))
    check("ledger protects branch", ledger_protects(led, "/elsewhere", "fix/a-b", "/Users/u"))
    check("ledger no false branch", not ledger_protects(led, "/elsewhere", "fix/a", "/Users/u"))
    check("ledger unreadable protects all", ledger_protects(None, "/x", "y", "/h"))
    now = 1000
    check("pause live honoured", not pause_is_stale(pause_flag_text(5, 2000), lambda p: True, now))
    check("pause dead pid stale", pause_is_stale(pause_flag_text(5, 2000), lambda p: False, now))
    check("pause expired stale", pause_is_stale(pause_flag_text(5, 900), lambda p: True, now))
    check("manual pause honoured", not pause_is_stale("paused by phill\n", lambda p: False, now))
    check("idle text", idle_from_text("output\n──\n❯ \n──\n status", 400)[0])
    check("busy text", not idle_from_text("✻ Working (esc to interrupt)\n❯ \n", 400)[0])
    check("typed text busy", not idle_from_text("x\n❯ half typed\n", 400)[0])
    check("question busy", not idle_from_text("Do you want to proceed?\n❯ 1. Yes\n", 400)[0])
    check("verdict word", classify_resume_text("**Verdict:** MINOR DRIFT") == "MINOR DRIFT")
    check("verdict phrase", classify_resume_text("Resume check: the tree matched the handoff exactly.").startswith("MATCH"))
    check("no verdict", classify_resume_text("Working on the rebase now.") is None)
    check("etime", parse_etime("01-15:09:45") == 86400 + 15 * 3600 + 9 * 60 + 45 and parse_etime("05:48") == 348)
    gj = json.dumps({"exit": 0, "drift": [], "manifest_sha": "x"})
    dj = json.dumps({"exit": 1, "drift": ["mini git: 2.53.0 DRIFT (want 2.56.0)"], "manifest_sha": "x"})
    check("fleet green", fleet_state(0, gj)["state"] == "GREEN")
    check("fleet drift", fleet_state(1, dj)["state"] == "DRIFT" and len(fleet_state(1, dj)["drift"]) == 1)
    check("fleet blocked only", fleet_state(2, json.dumps({"exit": 2, "drift": ["pc hermes"]}))["state"] == "BLOCKED")
    check("fleet garbage is unproven", fleet_state(0, "Traceback ...")["state"] == "UNPROVEN")
    check("fleet exit mismatch is unproven", fleet_state(0, dj)["state"] == "UNPROVEN")
    check("fleet crash code is unproven", fleet_state(124, "timeout after 300s")["state"] == "UNPROVEN")
    global MINI_SYSTEMS, NEEDS_MINI
    saved = (MINI_SYSTEMS, NEEDS_MINI)
    with tempfile.TemporaryDirectory() as d:
        MINI_SYSTEMS, NEEDS_MINI = d, d + "/NEEDS-PHILL.md"
        Path(NEEDS_MINI).write_text("# Needs Phill\n- LOST (estate-tidy, macbook): old row\n"
                                    "- LOST (estate-tidy, pc): pc row\n- LOST (estate-tidy, macbook): still lost\n"
                                    "- STALLED (estate-tidy): old stall\n- a note Phill wrote\n")
        Path(d, "tidy-macbook.json").write_text(json.dumps({"machine": "macbook", "lost": ["still lost"]}))
        Path(d, "tidy-pc.json").write_text("{ torn")
        fake = types.SimpleNamespace(machine="mini", dry=False, report={}, err=lambda *a: None)
        propagate_alerts(fake, [{"machine": "mini", "lost": ["new row"], "stalled": []}])
        out = Path(NEEDS_MINI).read_text()
        check("cleared alert removed", "old row" not in out and fake.report["alerts_cleared"])
        check("current alert kept once", out.count("still lost") == 1)
        check("unreadable report clears nothing", "pc row" in out)
        check("stall kept while a report is unreadable", "old stall" in out)
        check("new alert raised", "- LOST (estate-tidy, mini): new row" in out)
        check("non-alert lines untouched", "a note Phill wrote" in out and out.startswith("# Needs Phill\n"))
    MINI_SYSTEMS, NEEDS_MINI = saved
    print(json.dumps({"selftest": "FAIL" if fails else "PASS", "failed": fails}))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
