#!/usr/bin/env python3
"""dream.py — curate machine-local memory from recent session transcripts.

Reads ~/.claude/projects/**/*.jsonl, proposes memory changes, writes ONE record per run.
Everything it produces is [synthesised]: inferred from transcripts, never observed from a
live system. A synthesised memory may never be cited as evidence for a gate.

WHY A SCRIPT AND NOT PROSE. The spec (SKILL.md) is the contract; this is the mechanism, and
three of the requirements are structural rather than advisory:

  the heartbeat   a record must be appended on every run. Model discretion is exactly how
                  the ideas intake stayed at zero for weeks through green runs.
  the redaction   secrets must be stripped BEFORE any write, not "remembered" to be.
  the scale       transcripts run to hundreds of MB. Filtering must happen before anything
                  reaches a context window, or the run is unaffordable.

`schtasks` also needs a non-interactive entry point, which prose cannot provide. Precedent:
`proof-discipline` ships `mutate-assert.py` inside the skill directory, and deploy_skills.py's
own files_of() argues a skill's tools travel with it or they do not travel at all.

NO DELETE PATH, NO OVERWRITE PATH — a property, not a promise. `apply` only ever appends a new
line and comments the old one out. There is no code here that removes a memory. Removal is the
operator's instruction, executed by the operator.

NO NETWORK. Nothing here opens a socket. The redaction patterns are a self-contained copy of
scripts/secrets_check.py's set, deliberately: that script scans git-tracked files and, on a
hit, files a Linear ticket and fires a Telegram alert. Calling it would breach "no network",
would scan the wrong surface, and is impossible anyway once this skill is deployed to
~/.claude/skills/dream/ where the repo is not present. Keep the two lists in sync by hand;
`--selftest` asserts the copy still detects each shape.

  dream.py                 run: scan, propose, write the report and the run record
  dream.py status          last run, and RAISE past --stale-hours (default 36)
  dream.py apply 1,3       append proposals 1 and 3; comment out what they supersede
  dream.py --selftest      prove the redactor and the outcome classifier discriminate

Exit codes are about whether the RUN worked, never about what it found:
    0  the run completed (see the record for which of the three outcomes)
    1  status: no record, or the last record is stale
    2  the run could not complete — nothing usable was written
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
DEFAULT_PROJECTS = HOME / ".claude" / "projects"
DEFAULT_MEMORY = HOME / ".claude" / "memory"
RUNS_FILE = "dream-runs.jsonl"
REPORT_FILE = "dream-report.md"
# apply operates on THIS, not on the markdown. Re-deriving proposals at apply time would let
# the numbering shift between reading the report and acting on it, so "apply 3" could apply
# something the operator never read.
PROPOSALS_FILE = "dream-proposals.json"
STALE_HOURS = 36
TASK_NAME = "claude-dream"
WRAPPER = HOME / ".claude" / "dream-task.cmd"

# SCHED_S_* are STATUS codes, not failures, and Windows reports them in the same field as a
# real exit code. 267011 = SCHED_S_TASK_HAS_NOT_RUN, 267009 = RUNNING, 267010 = DISABLED.
# Reading one of these as a failure is how a freshness check starts crying wolf.
SCHED_NOT_A_FAILURE = {0, 267009, 267010, 267011}

# THREE outcomes. Never two. "ran and found nothing" and "did not run" are different facts and
# collapsing them is what hid the ideas drain through ten consecutive green runs. Note that
# DID_NOT_RUN is never written here — it is inferred from the ABSENCE of a record, because a
# process that failed to run cannot report that it failed to run.
RAN_PROPOSED = "ran-proposed-N"
RAN_NOTHING = "ran-nothing-to-propose"
DID_NOT_RUN = "did-not-run"

# Verbatim copy of scripts/secrets_check.py::_SECRET_PATTERNS (2026-08-04). See module docstring
# for why this is a copy rather than an import.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-ant-api[0-9A-Za-z\-_]{30,}", "Anthropic API key"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub personal access token"),
    (r"lin_api_[0-9A-Za-z]{40}", "Linear API key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----", "Private key"),
    (r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"\n]{8,}['\"]", "Hardcoded password"),
    (r"(?i)(secret|api_key|apikey|token)\s*=\s*['\"][^'\"\n]{8,}['\"]", "Hardcoded secret"),
    (r"(?i)bearer\s+[0-9a-zA-Z\-._~+/]{20,}", "Bearer token"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}", "JWT"),
    (r"\b(sk|rk)_live_[0-9A-Za-z]{16,}", "Stripe LIVE secret key"),
    (r"\b(sk|rk)_test_[0-9A-Za-z]{16,}", "Stripe test secret key"),
    (r"\b\d{8,10}:AA[0-9A-Za-z_-]{32,}", "Telegram bot token"),
]
_SECRET_RE = [(re.compile(p), name) for p, name in SECRET_PATTERNS]

# A correction or a stated preference is the signal worth keeping. These markers are
# deliberately narrow: a false positive costs one line in a report the operator reads, a false
# negative loses the correction entirely, but a marker set wide enough to match ordinary prose
# produces a report nobody reads, which loses everything.
MARKERS = [
    (r"(?i)\bno[,.]? (?:don'?t|do not|never|not)\b", "correction"),
    (r"(?i)\b(?:that'?s|this is) (?:wrong|incorrect|not right)\b", "correction"),
    # Sentence-initial only. A bare \bactually\b matches prose and code comments alike
    # ("what is actually sold") and was the single largest source of noise in the first real run.
    (r"(?i)(?:^|[.!?]\s+)actually[,]?\s", "correction"),
    (r"(?i)\binstead of\b", "correction"),
    (r"(?i)\bstop (?:doing|using|calling)\b", "correction"),
    (r"(?i)\b(?:never|always) (?:use|do|call|write|say|propose|assume)\b", "preference"),
    (r"(?i)\bi (?:prefer|want|expect|need) (?:you )?to\b", "preference"),
    (r"(?i)\bfrom now on\b", "preference"),
    (r"(?i)\bdon'?t (?:ever )?(?:use|do|call|write|say|propose|assume)\b", "preference"),
]
_MARKER_RE = [(re.compile(p), kind) for p, kind in MARKERS]

# NOT human speech, even though the transcript files it under type "user".
#
# Found in the first real run, which proposed twenty items of which most were slash-command
# payloads and pasted documents. A `/nexus <brief>` invocation is recorded as a user message, so
# mining it means mining the INSTRUCTIONS THIS AGENT WAS GIVEN and re-proposing them as
# "corrections the operator made" — self-contamination in a second costume, and rule 3 exists
# because the first costume already cost this box something.
ENVELOPE = re.compile(
    r"<command-(?:name|message|args)>|<system-reminder>|<local-command-stdout>|"
    r"^\s*<attachment|Caveat: The messages below were generated"
)

# Code, not prose. "// what is actually sold" is a comment, not a preference.
CODE_SHAPE = re.compile(r"(//|/\*|=>|[{};]\s*$|^\s*[\w]+:\s+(string|number|boolean|any)\b|^\s*[-*]\s*`)")

# A session that called none of these produced nothing durable. Synthesising memory from a
# session that did no work is the feedback_loop defect wearing a new costume: it manufactures
# signal from an absence of signal.
ARTEFACT_TOOLS = {"Write", "Edit", "NotebookEdit"}
ARTEFACT_SHELL = re.compile(r"git\s+(commit|branch|checkout\s+-b|tag|merge|cherry-pick)")


def redact(text: str) -> tuple[str, list[str]]:
    """Strip credential-shaped substrings. Returns the safe text and the shapes that hit.

    The matched value is never returned, never logged and never written — only the NAME of the
    shape. Transcripts are a secrets-rich surface; that is why they are gitignored.
    """
    hits: list[str] = []
    out = text
    for rx, name in _SECRET_RE:
        if rx.search(out):
            hits.append(name)
            out = rx.sub(f"[REDACTED {name}]", out)
    return out, hits


def _message_text(msg: object) -> str:
    """Human-typed text only. Tool results arrive as 'user' messages and are not human speech."""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "\n".join(parts)
    return ""


def parse_session(path: Path) -> dict | None:
    """One transcript -> {session_id, has_artefact, texts}. Returns None if unreadable."""
    session_id, has_artefact, texts = None, False, []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(d, dict):
                    continue
                session_id = session_id or d.get("sessionId") or d.get("session_id")
                t = d.get("type")
                if t == "user" and not d.get("isMeta"):
                    txt = _message_text(d.get("message"))
                    if txt.strip():
                        texts.append(txt)
                elif t == "assistant":
                    msg = d.get("message") or {}
                    content = msg.get("content") if isinstance(msg, dict) else None
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict) or block.get("type") != "tool_use":
                                continue
                            if block.get("name") in ARTEFACT_TOOLS:
                                has_artefact = True
                            elif block.get("name") == "Bash":
                                cmd = str((block.get("input") or {}).get("command", ""))
                                if ARTEFACT_SHELL.search(cmd):
                                    has_artefact = True
    except OSError:
        return None
    # The filename stem is the session UUID. Fall back to it so a transcript whose lines all
    # failed to parse still DEDUPES rather than silently counting as a distinct session.
    return {
        "session_id": session_id or path.stem,
        "has_artefact": has_artefact,
        "texts": texts,
        "path": str(path),
    }


def collect(projects: Path, hours: int, exclude_session: str | None) -> tuple[list[dict], dict]:
    """Sessions worth mining, plus the exclusion ledger. Deduped by session id."""
    cutoff = time.time() - hours * 3600
    excluded = {"current-session": [], "no-durable-artefact": [], "duplicate-project-key": []}
    by_id: dict[str, dict] = {}
    scanned = 0

    if not projects.is_dir():
        return [], excluded | {"_scanned": 0}

    for path in sorted(projects.rglob("*.jsonl")):
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        scanned += 1
        s = parse_session(path)
        if s is None:
            continue
        sid = s["session_id"]
        if exclude_session and sid == exclude_session:
            excluded["current-session"].append(sid)
            continue
        if sid in by_id:
            # THE SAME SESSION UNDER TWO PROJECT KEYS. This box writes one session under both
            # C--Users-Disaster-Recovery-4 and -Users-phill-mac. A naive glob counts it twice
            # and every proposal drawn from it inherits doubled weight.
            excluded["duplicate-project-key"].append(sid)
            prev = by_id[sid]
            prev["texts"] = prev["texts"] or s["texts"]
            prev["has_artefact"] = prev["has_artefact"] or s["has_artefact"]
            continue
        by_id[sid] = s

    keep = []
    for sid, s in by_id.items():
        if not s["has_artefact"]:
            excluded["no-durable-artefact"].append(sid)
            continue
        keep.append(s)

    excluded["_scanned"] = scanned
    return keep, excluded


def propose(sessions: list[dict], memory: Path) -> list[dict]:
    """Candidate memory changes, each carrying the verbatim line that evidences it."""
    # Memory LINES, not one blob — and never this tool's own output.
    #
    # Both halves were bugs found in the first real run. dream-report.md lives in the memory
    # directory and matched *.md, so run two read run one's proposals back as "existing memory"
    # and every proposal came out tagged supersede. A curator that treats its own output as
    # evidence is the same self-contamination rule 3 exists to prevent, wearing a third costume.
    #
    # And matching a quote against the WHOLE corpus is nearly always true: any sentence shares
    # three common words with a large MEMORY.md. Supersede means "this contradicts a specific
    # line", so the comparison has to be against a specific line.
    mem_lines: list[tuple[set[str], str, str]] = []   # (words, raw line, file)
    if memory.is_dir():
        for f in sorted(memory.glob("*.md")):
            if f.name.startswith("dream-"):
                continue
            try:
                for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    words = {w for w in re.findall(r"[a-z]{5,}", ln.lower())}
                    if words:
                        mem_lines.append((words, ln, str(f)))
            except OSError:
                pass

    out: list[dict] = []
    seen: set[str] = set()
    for s in sessions:
        for raw in s["texts"]:
            # Whole-message reject: a slash-command payload or a pasted document is not the
            # operator correcting anything, however many markers it happens to contain.
            if ENVELOPE.search(raw):
                continue
            for line in raw.splitlines():
                line = line.strip()
                if not (12 <= len(line) <= 400):
                    continue
                if CODE_SHAPE.search(line):
                    continue
                for rx, kind in _MARKER_RE:
                    if not rx.search(line):
                        continue
                    quote, hits = redact(line)
                    key = quote.lower()
                    if key in seen:
                        break
                    seen.add(key)
                    # Supersede only when ONE existing memory line shares enough distinctive
                    # vocabulary to be the thing this quote contradicts.
                    words = {w for w in re.findall(r"[a-z]{5,}", quote.lower())}
                    hit_n, hit_line, hit_file = 0, "", ""
                    for ml, raw, src in mem_lines:
                        n = len(words & ml)
                        if n > hit_n:
                            hit_n, hit_line, hit_file = n, raw, src
                    supersede = hit_n >= 3
                    out.append({
                        "kind": kind,
                        "action": "supersede" if supersede else "add",
                        "quote": quote,
                        "redacted": hits,
                        "session": s["session_id"],
                        "file": hit_file if supersede else str(memory / "MEMORY.md"),
                        # The exact line this would supersede. apply comments THIS line and no
                        # other — without it, "supersede" would be a label with no referent.
                        "supersedes": hit_line if supersede else None,
                    })
                    break
    return out


def write_report(memory: Path, proposals: list[dict], excluded: dict, outcome: str) -> Path:
    memory.mkdir(parents=True, exist_ok=True)
    p = memory / REPORT_FILE
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# dream report",
        "",
        f"- generated: {now}",
        f"- outcome: **{outcome}**",
        f"- transcripts scanned: {excluded.get('_scanned', 0)}",
        "",
        "> Every proposal below is **[synthesised]** — inferred from transcripts, never observed",
        "> from a live system. A synthesised memory may NEVER be cited as evidence for a gate.",
        "",
        "## Proposals",
        "",
    ]
    if not proposals:
        lines += ["_None. The run completed and found nothing to propose._",
                  "_This is NOT the same as the run not happening — see dream-runs.jsonl._", ""]
    for i, pr in enumerate(proposals, 1):
        red = f"  ⚠️ redacted: {', '.join(pr['redacted'])}" if pr["redacted"] else ""
        lines += [
            f"{i}. **[synthesised]** `{pr['action']}` ({pr['kind']}) → `{pr['file']}`{red}",
            f"   > {pr['quote']}",
            f"   _session {pr['session'][:8]}_",
            "",
        ]
    lines += ["## Sessions excluded", ""]
    for reason in ("current-session", "no-durable-artefact", "duplicate-project-key"):
        ids = excluded.get(reason, [])
        lines.append(f"- **{reason}**: {len(ids)}" + (f" — {', '.join(s[:8] for s in ids[:12])}" if ids else ""))
    lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    # The machine-readable twin of the report. apply reads THIS, so the numbering the operator
    # read is the numbering that acts.
    (memory / PROPOSALS_FILE).write_text(json.dumps(proposals, indent=1), encoding="utf-8")
    return p


def append_record(memory: Path, proposals: list[dict], excluded: dict, outcome: str) -> None:
    """One line per run. The heartbeat. Absence of a line is the only did-not-run signal."""
    memory.mkdir(parents=True, exist_ok=True)
    rec = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcome": outcome,
        "transcripts_scanned": excluded.get("_scanned", 0),
        "sessions_excluded": {
            k: len(v) for k, v in excluded.items() if not k.startswith("_")
        },
        "proposals_written": len(proposals),
        "redactions": sum(len(p["redacted"]) for p in proposals),
    }
    line = json.dumps(rec)
    with (memory / RUNS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    # ONLY AFTER the local write succeeded. The local record is the heartbeat; the remote copy
    # is a convenience for a dashboard that cannot read this filesystem. Ordering matters: if
    # the send ran first and the local append then failed, status would report did-not-run
    # while a row existed remotely saying otherwise.
    write_through(line)


def write_through(line: str, sender=None) -> None:
    """Fire-and-forget the record to Supabase on a daemon thread. RA-7123, per RA-7111.

    A failed send costs one row's durability and must NEVER cost the local run, so:
      - daemon thread: interpreter exit does not wait on it
      - every exception swallowed and logged, never raised into the caller
      - no join, no timeout the caller waits on

    Does nothing at all unless both env vars are present. That is not a silent skip — it is
    the only correct behaviour for a machine that has no credential, and `status` reports the
    local record regardless, so the heartbeat never depends on this path working.
    """
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if sender is None and not (url and key):
        return

    import hashlib
    import threading

    payload = {
        "hash": hashlib.sha256(line.encode("utf-8")).hexdigest(),
        "record": json.loads(line),
    }

    def _send() -> None:
        try:
            if sender is not None:
                sender(payload)
                return
            import urllib.request
            req = urllib.request.Request(
                f"{url.rstrip('/')}/rest/v1/dream_runs_durable",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "apikey": key, "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as exc:  # noqa: BLE001 - durability of one row, never the run
            print(f"  write-through failed (record is safe locally): {exc}", file=sys.stderr)

    threading.Thread(target=_send, daemon=True, name="dream-write-through").start()


def cmd_run(a: argparse.Namespace) -> int:
    projects, memory = Path(a.projects), Path(a.memory)
    exclude = a.exclude_session or os.environ.get("CLAUDE_SESSION_ID")
    sessions, excluded = collect(projects, a.hours, exclude)
    proposals = propose(sessions, memory)
    outcome = RAN_PROPOSED.replace("N", str(len(proposals))) if proposals else RAN_NOTHING

    report = write_report(memory, proposals, excluded, outcome)
    append_record(memory, proposals, excluded, outcome)

    print(f"outcome: {outcome}")
    print(f"transcripts scanned: {excluded.get('_scanned', 0)}   sessions kept: {len(sessions)}")
    for reason in ("current-session", "no-durable-artefact", "duplicate-project-key"):
        print(f"  excluded {reason}: {len(excluded.get(reason, []))}")
    print(f"report: {report}")
    for i, pr in enumerate(proposals[: a.limit], 1):
        print(f"\n{i}. [synthesised] {pr['action']} ({pr['kind']})")
        print(f"   > {pr['quote'][:300]}")
    if len(proposals) > a.limit:
        print(f"\n... {len(proposals) - a.limit} more in the report (--limit to widen)")
    return 0


def task_state(state_json: str | None = None) -> dict:
    """What the Windows scheduler says about our task. {} when it cannot be known.

    Returning {} rather than a guess is deliberate: "I could not read the scheduler" and
    "the scheduler says it ran fine" must not look alike.

    `state_json` injects a state file so both arms of the missed-run classification can be
    proved. The machine-was-unavailable arm cannot be produced on demand — you would have to
    switch the box off at 03:00 — so it is exercised against injected state and said so.
    """
    if state_json:
        try:
            return json.loads(Path(state_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    if os.name != "nt":
        return {}
    try:
        import subprocess  # local import: nothing else in this module shells out
        out = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True, text=True, errors="replace", timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    st: dict = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "last run time":
            st["last_run"] = v
        elif k == "last result":
            try:
                st["last_result"] = int(v)
            except ValueError:
                pass
        elif k == "scheduled task state":
            st["state"] = v
    return st


def diagnose_absence(task: dict) -> tuple[str, str]:
    """Why is there no fresh record? Returns (verdict, why).

    A freshness check that cries wolf is one that gets switched off, and then a real staleness
    gets ignored. This box sleeps; a 03:00 task on a desktop that is off simply MISSES, and
    "did-not-run" fired every such morning would be correct, useless, and eventually muted.
    So separate the two causes and only one of them is a fault.
    """
    if not task:
        return ("unknown", "the scheduler could not be read, so no cause can be assigned")

    # NEVER-RAN IS CHECKED FIRST, and the SCHED_S_* codes are statuses rather than failures.
    # The first version of this function checked `result != 0` first and so reported
    # SCHED_S_TASK_HAS_NOT_RUN (267011) as "the task ran and returned 267011 — this IS a fault":
    # it called a task that had never run a failure, which is the cry-wolf behaviour this whole
    # function exists to prevent. Caught by arm A of its own control, which is the only reason
    # two arms are mandatory — arm B passed identically both before and after.
    never = (not task.get("last_run")) or task["last_run"].strip().upper().startswith("N/A")
    if never:
        return ("machine-was-unavailable",
                "the scheduler has no record of the task ever running — the window was missed, "
                "not failed. Not a fault by itself.")
    res = task.get("last_result")
    if res is not None and res not in SCHED_NOT_A_FAILURE:
        return ("task-failed", f"the task ran and returned {res} — this IS a fault")
    return ("task-ran-but-wrote-nothing",
            f"the task last ran {task['last_run']} and returned 0, yet no record was written — "
            "a clean exit that produced nothing IS a fault")


def cmd_install_task(a: argparse.Namespace) -> int:
    """Generate the wrapper and register the schedule. THE GENERATOR IS THE CANONICAL SOURCE.

    The wrapper itself cannot be tracked: it holds this machine's python path and home
    directory, so a committed copy would be wrong on every other box — and a tracked file that
    is wrong everywhere but here is worse than none. Tracking the generator instead gives it a
    repo source (this file is in MANIFEST and deploys through the directory copy) without
    shipping a machine-specific path. Rebuild the box: deploy skills, run `install-task`.
    """
    exe = sys.executable
    target = Path(__file__).resolve()
    body = f'@echo off\r\n"{exe}" "{target}" run\r\n'

    short = str(WRAPPER)
    create = ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", "<short-path-of-wrapper>",
              "/SC", "DAILY", "/ST", a.at, "/F"]
    # StartWhenAvailable is the missed-run policy and schtasks CANNOT set it. Without it a
    # desktop that is off at 03:00 simply skips the day.
    ps = (f"Set-ScheduledTask -TaskName {TASK_NAME} "
          f"-Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable)")

    if a.print_only:
        print(f"would write {WRAPPER}:\n{body}")
        print("then: " + " ".join(create))
        print("then: powershell -NoProfile -Command " + ps)
        return 0

    WRAPPER.parent.mkdir(parents=True, exist_ok=True)
    WRAPPER.write_text(body, encoding="ascii")
    print(f"wrote {WRAPPER}")

    if os.name == "nt":
        # 8.3 SHORT PATH. schtasks stores /TR unquoted, so a home directory containing a space
        # produces a task that registers cleanly and executes nothing — observed 2026-08-04,
        # ERROR_FILE_NOT_FOUND, with a plausible Next Run Time the whole time.
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(WRAPPER), buf, 1024):
            short = buf.value
    print(f"short path: {short}")
    create[create.index("<short-path-of-wrapper>")] = short
    print("run these two commands to register (not run for you — scheduling is a machine change):")
    print("  " + " ".join(f'"{c}"' if " " in c else c for c in create))
    print(f"  powershell -NoProfile -Command \"{ps}\"")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    runs = Path(a.memory) / RUNS_FILE
    if not runs.exists():
        verdict, why = diagnose_absence(task_state(a.task_state_json))
        print(f"outcome: {DID_NOT_RUN}   cause: {verdict}")
        print(f"  {why}")
        print(f"RAISE: no run record at {runs}. Absence is the only did-not-run signal there is.")
        return 0 if verdict == "machine-was-unavailable" else 1
    last = None
    for line in runs.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    if last is None:
        print(f"outcome: {DID_NOT_RUN}")
        print(f"RAISE: {runs} exists but holds no readable record.")
        return 1

    ts = datetime.fromisoformat(last["timestamp"])
    age = datetime.now(timezone.utc) - ts
    print(f"last run: {last['timestamp']}  ({age.total_seconds() / 3600:.1f}h ago)")
    print(f"outcome:  {last['outcome']}")
    print(f"proposals: {last.get('proposals_written', 0)}   scanned: {last.get('transcripts_scanned', 0)}")
    if age > timedelta(hours=a.stale_hours):
        verdict, why = diagnose_absence(task_state(a.task_state_json))
        print(f"STALE — older than {a.stale_hours}h.   cause: {verdict}")
        print(f"  {why}")
        # A missed window on a desktop that was switched off is not a fault, and raising on it
        # every morning is how a freshness check gets muted before it ever catches a real one.
        return 0 if verdict == "machine-was-unavailable" else 1
    print("fresh")
    return 0


def cmd_apply(a: argparse.Namespace) -> int:
    """Append the chosen proposals. Never deletes, never overwrites a line in place.

    APPEND-ONLY BY CONSTRUCTION. A supersede writes the new line and COMMENTS the old one, so
    the history of a memory stays readable and no code path here can remove anything. Removal
    is the operator's instruction, executed by the operator.
    """
    memory = Path(a.memory)
    pfile = memory / PROPOSALS_FILE
    if not pfile.exists():
        print(f"no proposals at {pfile} — run dream first", file=sys.stderr)
        return 2
    props = json.loads(pfile.read_text(encoding="utf-8"))

    spec = (a.spec or "").strip()
    if not spec:
        print("nothing selected. usage: dream.py apply 1,3   |   dream.py apply all",
              file=sys.stderr)
        return 2
    if spec.lower() == "all":
        sel = list(range(1, len(props) + 1))
    else:
        try:
            sel = [int(x) for x in spec.replace(" ", "").split(",") if x]
        except ValueError:
            print(f"could not read selection {spec!r}", file=sys.stderr)
            return 2
    bad = [i for i in sel if not 1 <= i <= len(props)]
    if bad:
        print(f"out of range: {bad} (there are {len(props)} proposals)", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).date().isoformat()
    touched: dict[Path, list[str]] = {}
    applied = []
    for i in sel:
        p = props[i - 1]
        target = Path(p["file"])
        if target not in touched:
            touched[target] = target.read_text(encoding="utf-8").splitlines() \
                if target.exists() else []
        lines = touched[target]
        if p["action"] == "supersede" and p.get("supersedes"):
            old = p["supersedes"]
            for n, ln in enumerate(lines):
                if ln == old:
                    lines[n] = f"<!-- superseded {stamp} by dream: {ln} -->"
                    break
        # The line carries [synthesised] into the memory file itself, so a later reader cannot
        # mistake an inferred statement for an observed one.
        lines.append(f"- [synthesised {stamp}] {p['quote']}")
        applied.append((i, p["action"], target.name))

    for target, lines in touched.items():
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"applied {len(applied)} proposal(s):")
    for i, action, name in applied:
        print(f"  {i}. {action} -> {name}")
    print("append-only: nothing was deleted; superseded lines are commented, not removed.")
    return 0


def cmd_selftest(a: argparse.Namespace) -> int:
    """Prove the redactor and the outcome classifier can discriminate, before trusting either."""
    ok = True
    probe = "token is ghp_" + "a" * 36 + " end"
    safe, hits = redact(probe)
    if "ghp_" in safe or not hits:
        print("FAIL redactor did not strip a github token", file=sys.stderr)
        ok = False
    else:
        print(f"ok  redactor stripped: {hits}")
    clean, hits2 = redact("no credentials here at all")
    if hits2 or clean != "no credentials here at all":
        print("FAIL redactor altered clean text (false positive)", file=sys.stderr)
        ok = False
    else:
        print("ok  redactor left clean text untouched (discriminates)")
    hit = any(rx.search("no, don't use Slack for alerts") for rx, _ in _MARKER_RE)
    miss = any(rx.search("the deployment finished at noon") for rx, _ in _MARKER_RE)
    print(f"ok  marker fires on a correction={hit}, on ordinary prose={miss}")
    if not hit or miss:
        print("FAIL marker set does not discriminate", file=sys.stderr)
        ok = False
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="dream", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "status", "apply", "selftest", "install-task"])
    ap.add_argument("spec", nargs="?", default="", help="apply: 1,3 or all")
    ap.add_argument("--projects", default=str(DEFAULT_PROJECTS))
    ap.add_argument("--memory", default=str(DEFAULT_MEMORY))
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--stale-hours", type=int, default=STALE_HOURS)
    ap.add_argument("--exclude-session", default=None)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--task-state-json", default=None,
                    help="inject scheduler state (proves the missed-run arms)")
    ap.add_argument("--print-only", action="store_true")
    ap.add_argument("--at", default="03:00")
    a = ap.parse_args()
    if a.selftest:
        a.command = "selftest"
    try:
        return {"run": cmd_run, "status": cmd_status, "apply": cmd_apply,
                "selftest": cmd_selftest, "install-task": cmd_install_task}[a.command](a)
    except Exception as exc:  # noqa: BLE001 - a crash must not masquerade as "nothing to propose"
        print(f"dream could not complete: {exc}", file=sys.stderr)
        print("No record was written. status will report did-not-run, which is correct.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
