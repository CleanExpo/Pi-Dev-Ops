#!/usr/bin/env python3
"""Live ~/.claude drift alarm (2026-11-06). Stdlib only, runs under /usr/bin/python3 (3.9). No model, no paid API.
Fetches origin in the live checkout and compares HEAD with origin/main. Three states, never two:
  OK      even, or behind only by commits younger than 24h: marks row W-DRIFT-LIVE-CLAUDE-<host> done.
  FAIL    behind > 0 and the oldest missing commit (committer date) is older than 24h: writes or refreshes
          the row naming the behind count, that age and the ahead count.
  UNKNOWN the check could not run (not a git repo, fetch failed, rev-list failed) or the board is missing.
          It never resets a FAIL row (it only stamps unknown_since) and the reason is logged to stderr.
It also reads the nightly memory backup's status file (~/Library/Logs/claude-memory-backup.status, written by
Pi-Dev-Ops scripts/claude_memory_backup.sh as "OK <ts>" or "FAIL <ts> exit=N <error>", ts UTC %Y-%m-%dT%H:%M:%SZ)
into row W-MEMORY-BACKUP-<host>: FAIL when it reads FAIL, reads OK older than 36h, or is missing while the backup
LaunchAgent plist is installed; OK when a fresh OK; UNKNOWN when unreadable. Not installed and no file: no row.
Board writes go only through jobs_lock.update_jobs. When the board file is absent (the Mini volume is often not
mounted on the MacBook) a non-OK result is also sent as a macOS notification (best effort) and the exit is non-zero.
Exit codes: 0 OK recorded, 1 FAIL, 2 UNKNOWN (check or board).
Env seams (tests): LIVE_DRIFT_REPO, LIVE_DRIFT_OPS, LIVE_DRIFT_HOST, LIVE_DRIFT_GIT, LIVE_DRIFT_NOTIFY
(notifier executable taking one message argument; default osascript), LIVE_DRIFT_MAX_AGE_H, LIVE_DRIFT_TIMEOUT,
LIVE_DRIFT_BACKUP_STATUS, LIVE_DRIFT_BACKUP_PLIST, LIVE_DRIFT_BACKUP_MAX_AGE_H."""
import datetime, os, re, socket, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs_lock

REPO = os.environ.get("LIVE_DRIFT_REPO", os.path.expanduser("~/.claude"))
OPS = os.environ.get("LIVE_DRIFT_OPS", "/Volumes/Mini Mini 2T Storage/ops")
HOST = re.sub(r"[^A-Za-z0-9-]", "-", os.environ.get("LIVE_DRIFT_HOST") or socket.gethostname().split(".")[0])
GIT = os.environ.get("LIVE_DRIFT_GIT", "/usr/bin/git")
NOTIFY = os.environ.get("LIVE_DRIFT_NOTIFY", "")
MAX_AGE_H = float(os.environ.get("LIVE_DRIFT_MAX_AGE_H", "24"))
TIMEOUT = float(os.environ.get("LIVE_DRIFT_TIMEOUT", "120"))
ROW = "W-DRIFT-LIVE-CLAUDE-" + HOST
BACKUP_STATUS = os.environ.get("LIVE_DRIFT_BACKUP_STATUS", os.path.expanduser("~/Library/Logs/claude-memory-backup.status"))
BACKUP_PLIST = os.environ.get("LIVE_DRIFT_BACKUP_PLIST",
                              os.path.expanduser("~/Library/LaunchAgents/com.phillmcgurk.claude-memory-backup.plist"))
BACKUP_MAX_AGE_H = float(os.environ.get("LIVE_DRIFT_BACKUP_MAX_AGE_H", "36"))
BACKUP_ROW = "W-MEMORY-BACKUP-" + HOST
TS = "%Y-%m-%dT%H:%M%z"
NOW = datetime.datetime.now().astimezone().strftime(TS)
OK, FAIL, UNKNOWN = "OK", "FAIL", "UNKNOWN"


def git(*args):
    """(ok, stdout, reason). Never prompts for credentials."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        r = subprocess.run([GIT, "-C", REPO, *args], capture_output=True, text=True, timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return False, "", "timed out after %gs" % TIMEOUT
    except Exception as e:
        return False, "", "could not run git: %s: %s" % (type(e).__name__, e)
    if r.returncode != 0:
        line = next((l.strip() for l in r.stderr.splitlines() if l.strip()), "")
        return False, "", "exit %d: %s" % (r.returncode, line)
    return True, r.stdout, ""


def check():
    """(state, message, fields)."""
    ok, out, _ = git("rev-parse", "--is-inside-work-tree")
    if not ok or out.strip() != "true":
        return UNKNOWN, "%s is not a git repo" % REPO, {}
    ok, _, why = git("fetch", "--quiet", "--no-tags", "origin")
    if not ok:
        return UNKNOWN, "git fetch origin failed in %s: %s" % (REPO, why), {}
    counts = {}
    for key, rng in (("behind", "HEAD..origin/main"), ("ahead", "origin/main..HEAD")):
        ok, out, why = git("rev-list", "--count", rng)
        if not ok or not out.strip().isdigit():
            return UNKNOWN, "rev-list %s failed in %s: %s" % (rng, REPO, why or out.strip()), {}
        counts[key] = int(out.strip())
    behind, ahead = counts["behind"], counts["ahead"]
    if behind == 0:
        return OK, "", counts
    ok, out, why = git("log", "--format=%ct", "HEAD..origin/main")
    stamps = [int(s) for s in out.split() if s.isdigit()] if ok else []
    if len(stamps) != behind:
        return UNKNOWN, "could not read commit dates of HEAD..origin/main in %s: %s" % (REPO, why or "count mismatch"), {}
    age_h = (time.time() - min(stamps)) / 3600.0
    counts["age_hours"] = round(age_h, 1)
    if age_h <= MAX_AGE_H:
        return OK, "", counts
    return FAIL, ("~/.claude on %s is %d commits behind origin/main, oldest missing commit %.0fh old, %d ahead; "
                  "run git pull --rebase there" % (HOST, behind, age_h, ahead)), counts


def check_backup():
    """(state, message, fields) for the nightly memory backup's status file."""
    try:
        line = open(BACKUP_STATUS).readline().strip()
    except FileNotFoundError:
        if os.path.exists(BACKUP_PLIST):
            return FAIL, "memory backup on %s: status file %s missing although %s is installed" % (
                HOST, BACKUP_STATUS, BACKUP_PLIST), {}
        return OK, "", {}
    except Exception as e:
        return UNKNOWN, "memory backup status %s unreadable: %s: %s" % (BACKUP_STATUS, type(e).__name__, e), {}
    parts = line.split(" ", 2)
    try:
        when = datetime.datetime.strptime(parts[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (IndexError, ValueError):
        when = None
    shape_ok = (parts[0] == OK and len(parts) == 2) or (
        parts[0] == FAIL and len(parts) == 3 and re.match(r"exit=\d+(\s|$)", parts[2]) is not None)
    if not shape_ok or when is None:
        return UNKNOWN, "memory backup status %s not in 'OK <ts>' / 'FAIL <ts> exit=N <error>' form: %r" % (
            BACKUP_STATUS, line[:80]), {}
    if parts[0] == FAIL:
        return FAIL, "memory backup on %s failed: %s" % (HOST, line), {}
    age_h = (time.time() - when.timestamp()) / 3600.0
    if age_h > BACKUP_MAX_AGE_H:
        return FAIL, "memory backup on %s last succeeded %.0fh ago (%s), over %gh" % (
            HOST, age_h, parts[1], BACKUP_MAX_AGE_H), {"age_hours": round(age_h, 1)}
    return OK, "", {}


def apply(d, row, state, msg, fields):
    jobs = {j.get("id"): j for j in d["jobs"]}
    j = jobs.get(row)
    if state == OK:
        if j is None or (j.get("status") == "done" and j.get("check_state") == OK):
            return False
        j.update({"status": "done", "updated": NOW, "blocker": "", "check_state": OK, "unknown_since": None,
                  "last_known_good_at": NOW})
        return True
    if state == FAIL:
        new = {"title": "ALERT: " + msg, "updated": NOW, "status": "open", "blocker": msg, "check_state": FAIL,
               "priority": "P2", "unknown_since": None, **fields}
        if j is None:
            d["jobs"].append({"id": row, "owner": "Live drift alarm", "created": NOW, **new})
        else:
            j.update(new)
        return True
    # UNKNOWN: an open FAIL row stays exactly as it was, only stamped
    if j is not None and j.get("status") != "done" and j.get("check_state") == FAIL:
        if j.get("unknown_since"):
            return False
        j["unknown_since"] = NOW
        return True
    text = "check could not run: " + msg
    new = {"title": "ALERT: " + text, "updated": NOW, "status": "open", "blocker": text, "check_state": UNKNOWN,
           "priority": "P3", "unknown_since": (j or {}).get("unknown_since") or NOW}
    if j is None:
        d["jobs"].append({"id": row, "owner": "Live drift alarm", "created": NOW, **new})
    else:
        j.update(new)
    return True


def notify(msg):
    """Best effort; a failed notification is logged, never raised."""
    try:
        if NOTIFY:
            subprocess.run([NOTIFY, msg], timeout=30, capture_output=True)
        else:
            script = 'display notification "%s" with title "Live ~/.claude drift"' % msg.replace("\\", "").replace('"', "'")
            subprocess.run(["/usr/bin/osascript", "-e", script], timeout=30, capture_output=True)
    except Exception as e:
        print("notification failed: %s: %s" % (type(e).__name__, e), file=sys.stderr)


def main():
    results = [(ROW,) + check(), (BACKUP_ROW,) + check_backup()]
    for row, state, msg, fields in results:
        print("%s %s %s %s" % (NOW, row, state, msg or fields), file=sys.stderr)
    states = {state for _, state, _, _ in results}
    board = os.path.join(OPS, "jobs.json")
    if not os.path.isfile(board):
        print("board %s not found; result not recorded" % board, file=sys.stderr)
        for _, state, msg, _ in results:
            if state != OK:
                notify(msg)
        return 1 if FAIL in states else 2
    jobs_lock.update_jobs(board, lambda d: any([apply(d, *r) for r in results]))
    return 1 if FAIL in states else 2 if UNKNOWN in states else 0


if __name__ == "__main__":
    sys.exit(main())
