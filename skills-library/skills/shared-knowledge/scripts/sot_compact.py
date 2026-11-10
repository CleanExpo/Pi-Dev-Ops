#!/usr/bin/env python3
"""Read new lines of the append-only ops/lessons-staging.jsonl into the quarantine, and merge only founder-approved lessons into
SHARED-KNOWLEDGE.md (AUTO LESSONS block), dedupe, cap 40. Grok Bot 2026-10-26.

26/10/2026 (specialist-board spec AC-14): every staged lesson used to reach SHARED-KNOWLEDGE, which every
session on every machine reads at start. Now a lesson stays in lessons-quarantine.jsonl until an approval
Phill approves it from his own Terminal:
    sot_compact.py list            pending lessons, each with its id, source and outside-content marker
    sot_compact.py approve <id>    approve and merge (refused without a terminal: agents cannot approve)
The unattended launchd compact never promotes and never reads lessons-approvals.jsonl, which is an audit
log only: an event any same-user process can append must not be what the background job acts on (review
r1 P1). Residual: a same-user process can still write SHARED-KNOWLEDGE.md itself; closing that needs an OS
user boundary, which is founder-gated."""
import json, os, re, sys, time, fcntl, hashlib, calendar
OPS = os.environ.get("SOT_OPS", "/Volumes/Mini Mini 2T Storage/ops")
SK, ST = OPS + "/SHARED-KNOWLEDGE.md", OPS + "/lessons-staging.jsonl"
Q, APPROVALS = OPS + "/lessons-quarantine.jsonl", OPS + "/lessons-approvals.jsonl"
CUR = OPS + "/.lessons-staging.cursor"   # bytes of staging already in the quarantine
# RSI intake filter (09/11/2026): 44% of 3,666 staged rows were noise (a closing tag captured into the lesson, the
# same text re-sent by a scheduled job every run, page alerts sent down the lesson channel). Every writer, the hook
# and site_watch.mjs alike, reaches the quarantine only through compact(), so the filter lives there, once.
REPEATS, NONLESSON = OPS + "/lessons-repeats.jsonl", OPS + "/lessons-nonlesson.jsonl"
KINDS = OPS + "/lesson-kinds.json"   # agent-written kind proposals; nothing in them counts until Phill approves on a terminal
NON_LESSON_TOOLS = {"site-watch"}   # status output, not lessons
DEDUPE_DAYS = 14
TAG_TAIL = re.compile(r"(\s*</[A-Za-z][\w:-]*>)+\s*$")
def clean(s): return TAG_TAIL.sub("", s).strip()
A, Z = "<!-- AUTO-LESSONS:START -->", "<!-- AUTO-LESSONS:END -->"; CAP = 40
def norm(s): return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
def mounted():
    parts = OPS.split("/")
    return os.path.isdir(OPS) and (not OPS.startswith("/Volumes/") or os.path.ismount("/".join(parts[:3])))
def read_lines(path):
    """Review r6: a crash halfway through a multi-byte character leaves bytes a strict decode refuses, and every
    later compact, list and approve died on them. Undecodable bytes become U+FFFD; the torn line then fails
    json.loads and is skipped like any other fragment, and the rows around it are read as before."""
    return open(path, encoding="utf-8", errors="replace")
def rows(path):
    if not os.path.isfile(path): return []
    out = []
    for l in read_lines(path):
        try: r = json.loads(l)
        except ValueError: continue
        if isinstance(r, dict) and isinstance(r.get("lesson"), str): out.append(r)
    return out
def rows_any(path):
    if not os.path.isfile(path): return []
    out = []
    for l in read_lines(path):
        try: r = json.loads(l)
        except ValueError: continue
        if isinstance(r, dict): out.append(r)
    return out
def locked():
    lk = open(OPS + "/.sot-compact.lock", "a"); fcntl.flock(lk, fcntl.LOCK_EX); return lk
def write_rows(path, rs):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        for r in rs: f.write(json.dumps(r) + "\n")
    os.replace(path + ".tmp", path)
# Same as sot_hook.append_lines: the two scripts are installed separately (compact on the Mini only), so each
# carries its own copy rather than importing the other.
def append_lines(path, lines):
    """Append whole lines and fsync. A crash mid-append leaves a last line with no newline; appending onto it
    would fuse the next line into one unreadable line, so close it off first (review r3/r4: staging, spool
    and quarantine all append, so all three use this). Caller holds the file's lock."""
    torn = False
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END); torn = f.read(1) != b"\n"
    with open(path, "a", encoding="utf-8") as f:
        if torn: f.write("\n")
        for l in lines: f.write(l + "\n")
        f.flush(); os.fsync(f.fileno())
def stamp(ts):
    """Epoch seconds of a row's ts, or None. Writers use '+1000' and '+10:00' offsets, with or without seconds."""
    if not isinstance(ts, str): return None
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)([+-]\d{2}):?(\d{2})$", ts.strip())
    if not m: return None
    try:
        d = time.strptime(m.group(1) + (":00" if len(m.group(1)) == 16 else ""), "%Y-%m-%dT%H:%M:%S")
    except ValueError: return None
    off = (int(m.group(2)) * 60 + (1 if m.group(2)[0] != "-" else -1) * int(m.group(3))) * 60
    return calendar.timegm(d) - off
def cursor():
    try: return max(0, int(open(CUR).read().strip()))
    except (OSError, ValueError): return 0
def compact():
    """Staging is append-only and never moved. CUR is how far it has been read; it moves only after the new
    rows are durably in the quarantine, so a crash re-reads (deduped by id) and never loses a line. An old
    writer still holding staging open keeps appending to the same file, which the next run reads."""
    if not mounted(): raise SystemExit(0)   # never create the ops tree on the internal disk
    lk = locked()
    q = rows(Q)
    known = {r.get("id") for r in q}
    known |= {r.get("id") for r in rows_any(REPEATS) + rows_any(NONLESSON)}
    latest = {}   # normalised text -> (id, epoch) of the row a repeat is counted against: the newest window start
    for r in q:
        k, t = norm(r.get("lesson", "")), stamp(r.get("ts"))
        if k and t is not None and (k not in latest or latest[k][1] is None or t > latest[k][1]): latest[k] = (r.get("id"), t)
    new, repeats, nonlesson = [], [], []
    start = cursor()
    size = os.path.getsize(ST) if os.path.isfile(ST) else 0
    if start > size: start = 0   # staging was replaced by hand: read it again, ids dedupe
    chunk = b""
    if size:
        with open(ST, "rb") as f:
            f.seek(start); chunk = f.read()
    end = chunk.rfind(b"\n") + 1   # a line still being written waits for the next run
    for l in chunk[:end].decode("utf-8", "replace").splitlines():
        try: r = json.loads(l)
        except ValueError: continue
        if not (isinstance(r, dict) and isinstance(r.get("lesson"), str)): continue
        # whatever a writer sent: the status is quarantined, no source means unverified
        r["status"] = "quarantined"
        r.setdefault("source", "unverified"); r.setdefault("read_external", ["unknown"])
        r.setdefault("id", hashlib.sha256(("%s|%s|%s|%s" % (r.get("ts"), r.get("machine"), r.get("tool"), r["lesson"])).encode()).hexdigest()[:16])
        if r["id"] in known: continue
        known.add(r["id"])
        r["lesson"] = clean(r["lesson"])
        if r.get("tool") in NON_LESSON_TOOLS: nonlesson.append(r); continue
        k, t = norm(r["lesson"]), stamp(r.get("ts"))
        first = latest.get(k)
        if k and first and t is not None and first[1] is not None and 0 <= t - first[1] < DEDUPE_DAYS * 86400:
            repeats.append({"of": first[0], "id": r["id"], "ts": r.get("ts"), "machine": r.get("machine"), "tool": r.get("tool")})
            continue
        if k: latest[k] = (r["id"], t)
        new.append(r)
    # Order matters for a crash: side files first, quarantine next, CUR last. A re-read finds every id in `known`
    # only once it is in the quarantine, so a crash after a side write may repeat that side line, never lose a lesson.
    if repeats: append_lines(REPEATS, [json.dumps(r) for r in repeats])
    if nonlesson: append_lines(NONLESSON, [json.dumps(r) for r in nonlesson])
    if new:
        append_lines(Q, [json.dumps(r) for r in new])   # a torn fragment's lesson is still unread in staging; CUR moves after
    if end:
        with open(CUR + ".tmp", "w") as f: f.write(str(start + end))
        os.replace(CUR + ".tmp", CUR)
    lk.close()
    print("pending", sum(1 for r in q + new if r.get("status") == "quarantined"))
def write_auto(entries):
    """Write (tag, text) lines into the AUTO LESSONS block, newest first, deduped by normalised text, capped.
    Takes text, never quarantine rows, so a kind rule cannot share an id with a lesson (review r1 P1). Caller holds the lock."""
    sk = open(SK, encoding="utf-8").read()
    if A not in sk: sk = sk.rstrip() + "\n\n## AUTO LESSONS (founder-approved lessons from every machine/agent, merged by sot_compact.py; newest first, max %d)\n%s\n%s\n" % (CAP, A, Z)
    pre, rest = sk.split(A, 1); body, post = rest.split(Z, 1)
    old = [l for l in body.strip().splitlines() if l.startswith("- ")]
    seen = set(norm(re.sub(r"^- \[[^\]]*\] ", "", l)) for l in old)
    seen |= set(norm(l) for l in pre.splitlines())
    add = []
    for tag, text in entries:
        k = norm(text)
        if k and k not in seen: seen.add(k); add.append("- [%s] %s" % (tag, text))
    lines = (add[::-1] + old)[:CAP]
    open(SK + ".tmp", "w", encoding="utf-8").write(pre + A + "\n" + "\n".join(lines) + "\n" + Z + post); os.replace(SK + ".tmp", SK)
    return len(add)
def merge(q, ok):
    """Write the pending lessons whose id is in ok into the AUTO LESSONS block; return q with those marked approved.
    Rows are never dropped: a re-read of staging after a crash finds their id and adds nothing. Caller holds the lock."""
    ok = {i for i in ok if any(r.get("id") == i and r.get("status") == "quarantined" for r in q)}
    promote = [r for r in q if r.get("id") in ok]
    if promote:
        write_auto([("%s %s/%s" % (str(r.get("ts", ""))[:10], r.get("machine"), r.get("tool")), r["lesson"])
                    for r in promote if not r["lesson"].endswith("…")])
    print("promoted", len(promote))
    return [dict(r, status="approved") if r.get("id") in ok else r for r in q]
def load_kinds():
    """(kinds by key, id -> key) from the agent-written proposal file. Malformed entries are skipped, not trusted;
    text is capped so a proposal cannot push a wall of text into SHARED-KNOWLEDGE."""
    try: d = json.load(open(KINDS, encoding="utf-8"))
    except (OSError, ValueError): return {}, {}
    ks = {}
    for k in d.get("kinds", []) if isinstance(d, dict) else []:
        if not isinstance(k, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,12}", str(k.get("key", ""))): continue
        if not all(isinstance(k.get(f), str) and k[f].strip() for f in ("name", "definition", "design_change")): continue
        ks[k["key"]] = {f: " ".join(k[f].split())[:240] for f in ("name", "definition", "design_change")}
    a = d.get("assign") if isinstance(d, dict) else None
    return ks, ({i: v for i, v in a.items() if isinstance(i, str) and v in ks} if isinstance(a, dict) else {})
def kind_rule(k): return "%s: %s Fix: %s" % (k["name"], k["definition"], k["design_change"])
def founder_terminal():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("refused: only from Phill's own Terminal (no terminal attached)", file=sys.stderr); raise SystemExit(2)
    if not mounted(): print("refused: ops folder not mounted: %s" % OPS, file=sys.stderr); raise SystemExit(2)
def kind_decision(mode, key):
    """approve-kind: one rule line per kind goes into AUTO LESSONS and the kind's pending lessons are marked approved.
    reject-kind: the kind's pending lessons are marked rejected and nothing is merged. Terminal only, like approve."""
    founder_terminal()
    lk = locked()
    ks, assign = load_kinds()
    if key not in ks:
        lk.close(); print("refused: unknown kind: %s (see: sot_compact.py kinds)" % (key or "none given"), file=sys.stderr); raise SystemExit(2)
    q = rows(Q)
    ids = [r.get("id") for r in q if r.get("status") == "quarantined" and assign.get(r.get("id")) == key]
    if mode == "approve-kind":
        rule = kind_rule(ks[key])
        write_auto([("%s kind %s/%d lessons" % (time.strftime("%Y-%m-%d"), key, len(ids)), rule)])
        print("merged:", rule)
    status = "approved" if mode == "approve-kind" else "rejected"
    members = set(ids)
    q = [dict(r, status=status) if r.get("id") in members else r for r in q]
    write_rows(Q, q)
    with open(APPROVALS, "a") as f:   # audit log only; nothing reads it to decide
        f.write(json.dumps({"kind": key, "ids": ids, "status": status, "by": "founder", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
    lk.close()
    print("%s %d lessons in %s" % (status, len(ids), key))
def list_kinds():
    ks, assign = load_kinds()
    if not ks: print("no kind proposals at %s" % KINDS); return
    pend = [r for r in rows(Q) if r.get("status") == "quarantined"]
    print("Agent-written kind proposals: read each rule before approving it.\n")
    for key, k in ks.items():
        mem = [r for r in pend if assign.get(r.get("id")) == key]
        print("%s  %s  (%d pending)\n    rule: %s" % (key, k["name"], len(mem), kind_rule(k)))
        for r in mem[:3]: print("    e.g. %s" % r["lesson"][:160])
        print()
    print("approve: sot_compact.py approve-kind <KEY>    reject: sot_compact.py reject-kind <KEY>")
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "kinds": list_kinds(); return
    if mode in ("approve-kind", "reject-kind"): kind_decision(mode, sys.argv[2] if len(sys.argv) > 2 else ""); return
    if mode == "list":
        for r in rows(Q):
            if r.get("status") != "quarantined": continue
            ext = r.get("read_external") or []
            print("%s  [%s %s/%s] source=%s%s\n    %s" % (r.get("id"), str(r.get("ts", ""))[:10], r.get("machine"), r.get("tool"), r.get("source"),
                  "  OUTSIDE CONTENT: " + ",".join(ext) if ext else "", r["lesson"]))
        return
    if mode == "approve":
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("refused: approve only from Phill's own Terminal (no terminal attached)", file=sys.stderr); raise SystemExit(2)
        if not mounted(): print("refused: ops folder not mounted: %s" % OPS, file=sys.stderr); raise SystemExit(2)
        ids = sys.argv[2:]
        lk = locked()
        q = rows(Q)
        missing = [i for i in ids if i not in {r.get("id") for r in q if r.get("status") == "quarantined"}]
        if not ids or missing:
            lk.close(); print("refused: unknown id(s): %s" % (" ".join(missing) or "none given"), file=sys.stderr); raise SystemExit(2)
        write_rows(Q, merge(q, set(ids)))
        with open(APPROVALS, "a") as f:   # audit log only; nothing reads it to decide
            for i in ids: f.write(json.dumps({"id": i, "status": "approved", "by": "founder", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
        lk.close()
        return
    compact()
if __name__ == "__main__":
    main()
