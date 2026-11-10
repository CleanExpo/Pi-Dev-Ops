#!/usr/bin/env python3
"""Jev/TypeSafe spend watcher (Guardian 2026-10-26). No model, no paid API.
Sums today's spend from the canonical Jev spend ledger (JEV_SPEND_LEDGER, default ~/.local/state/jev/spend.sqlite) plus the Mission Control ledger. Alerts once per day per threshold
(80% and 100% of cap) via the Hermes home Telegram bot and a W-TYPESAFE-CAP job in ops/jobs.json.
Ledger day = UTC date (that's how the ledgers key spend).
A ledger that is missing, unreadable, corrupt or lacks the expected column is NOT $0: the day is UNKNOWN,
the total is a lower bound, and W-TYPESAFE-CAP-UNKNOWN names the failing ledger(s).
An alert level is recorded as sent only when Telegram confirmed delivery; two failed runs in a row raise W-ALERT-DELIVERY.
Both ledgers are required in every run and both are read as SQLite only: nothing can replace or drop one, and a
file of any other format at either path is unreadable (UNKNOWN). JEV_SPEND_LEDGER (the writer's own variable) and
JEV_WATCH_MC_LEDGER move a ledger, never remove it. JEV_WATCH_LEDGERS, the old replacement list, is not read: setting
it is reported as UNKNOWN so a leftover override cannot quietly change what the cap counts.
Env overrides for testing: JEV_WATCH_MC_LEDGER, JEV_WATCH_OPS, JEV_WATCH_STATE, JEV_WATCH_DRY=1,
JEV_WATCH_CAP, JEV_WATCH_SQLITE_TIMEOUT (seconds). Tests also replace telegram() with a fake returning (ok, detail)."""
import json, math, os, sqlite3, sys, datetime, tempfile, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs_lock
def _ledger(var, default):
    """A ledger path from env var `var`, else `default`. Same rule as the Pi-Dev-Ops writer (jev_platform/spend.py,
    RA-8116): a blank or relative override is unusable, and an unusable path is reported as an unreadable ledger
    (UNKNOWN), never skipped and never silently replaced by the default."""
    raw = os.environ.get(var)
    return os.path.expanduser(default) if raw is None else _usable(var, raw)
class Rejected(str):
    """An override that names no usable ledger. It is a label for the UNKNOWN blocker, never a filesystem path:
    spent_today reports it without touching the disk, so a file that happens to share its name is never read."""
def _usable(var, raw):
    path = os.path.expanduser(raw)
    return path if raw.strip() and os.path.isabs(path) else Rejected(f"{var}-unusable[{raw}]")
CAP = float(os.environ.get("JEV_WATCH_CAP", "20"))
# Two ledgers, both required. The old per-checkout Pi-Dev-Ops ledgers are gone: every Pi-Dev-Ops Jev caller now records in the canonical one.
# Mission Control keeps its own ledger too; a row it mirrored into the canonical ledger carries that row's call_id as
# spend_call_id and is counted once, at the larger of the two amounts (see spent_today).
MC_LEDGER = _ledger("JEV_WATCH_MC_LEDGER", "/Volumes/Mini Mini 2T Storage/ops/jev/mission-control-jev-ledger.sqlite")
LEDGERS = [_ledger("JEV_SPEND_LEDGER", "~/.local/state/jev/spend.sqlite"), MC_LEDGER]
MC_CALLER = "mission_control_jev_shadow"   # the caller Pi-Dev-Ops scripts/jev_shadow_support.py writes for these rows
# Review r4 (28/10/2026): a one-item replacement list dropped both required ledgers and closed UNKNOWN. No list replaces them now.
LIST_SET = "JEV_WATCH_LEDGERS" in os.environ
OPS = os.environ.get("JEV_WATCH_OPS", "/Volumes/Mini Mini 2T Storage/ops")
STATE = os.environ.get("JEV_WATCH_STATE", os.path.expanduser("~/.local/state/jev-cap-watcher.json"))
DRY = os.environ.get("JEV_WATCH_DRY") == "1"
SQLITE_TIMEOUT = float(os.environ.get("JEV_WATCH_SQLITE_TIMEOUT", "5"))
MAX_AMOUNT = 1e6   # dollars per ledger entry
DAY = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
NOW = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")

def _amount(v):
    """A ledger amount must be a real, finite, non-negative number. NaN, inf, a bool or a string
    would poison the total (and be written to state as NaN), so the ledger is UNKNOWN instead."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise ValueError(f"spend value {v!r} is not a finite non-negative number")
    if v > MAX_AMOUNT:   # no real call costs this; also makes overflow of the sum impossible
        raise ValueError(f"spend value {v!r} is above the plausible ceiling ${MAX_AMOUNT:,.0f}")
    return float(v)

def spent_today():
    """Returns (total_of_readable_ledgers, [(path, reason)] for every ledger that could not be read)."""
    total, bad = 0.0, []
    if LIST_SET:
        bad.append(("JEV_WATCH_LEDGERS", "set, not read: the two required ledgers cannot be replaced"))
    ledgers = LEDGERS
    try:   # two names for one file would read one required ledger twice and the other not at all
        if all(os.path.isabs(p) and os.path.exists(p) for p in LEDGERS) and os.path.samefile(*LEDGERS):
            bad.append((LEDGERS[1], "same file as the spend ledger, so the Mission Control ledger is not read")); ledgers = LEDGERS[:1]
    except OSError as e:
        bad.append((LEDGERS[1], f"cannot compare with the spend ledger: {type(e).__name__}")); ledgers = LEDGERS[:1]
    canonical_ids = {}   # call_id -> (amount, caller, reserve) for today's spend-ledger rows (read first); MC's spend_call_id names one
    for p in ledgers:
        if isinstance(p, Rejected) or not os.path.isabs(p):   # checked before any filesystem access
            bad.append((str(p), "unusable override, not read")); continue
        if not os.path.exists(p):
            bad.append((p, "missing")); continue
        try:
            # SQLite only, whatever the file is called: a JSON (or any other) file here fails to open and is UNKNOWN.
            # Quoted, so a '?' or '#' in the path is part of the file name, not URI syntax naming another file.
            db = sqlite3.connect(f"file:{urllib.parse.quote(p)}?mode=ro", uri=True, timeout=SQLITE_TIMEOUT)
            try:
                # Row by row: SUM() would coerce text to 0 and let a negative row cancel a real one. Every row's amount
                # is checked before any dedupe (review r2, d5eb03fa).
                # A Mission Control call mirrored into the canonical ledger is one call in two places. The only identity
                # that survives a canonical reset is the random call_id the spend ledger gives each row; the mirror
                # keeps it as spend_call_id (Pi-Dev-Ops RA-8116). Row numbers, callers and reserves repeat after a reset
                # (review r3, d191f9cf), so they never match a pair. A matched pair counts the larger of its two amounts
                # (the canonical one is already in the total, so only the excess is added), and one canonical call
                # absorbs at most one mirror row. A row with no spend_call_id, a ledger without the columns, or an id
                # not in today's canonical rows is counted in full: an overcount is safe, an undercount hides spend.
                cols = {r[1] for r in db.execute("PRAGMA table_info(calls)")}
                own = "call_id" if "call_id" in cols else "NULL"
                link = "spend_call_id" if "spend_call_id" in cols else "NULL"
                caller = "caller" if "caller" in cols else "NULL"
                rows = db.execute(f"SELECT COALESCE(actual_usd, reserved_usd), {own}, {link}, {caller}, reserved_usd "
                                  "FROM calls WHERE day=?", (DAY,)).fetchall()
                # Nothing from this ledger is kept until every row has passed, so an unreadable canonical ledger
                # leaves no ids behind to discount Mission Control rows against spend that was never counted.
                sub, seen, absorbed = 0.0, {}, set()
                for a, cid, twin, who, res in rows:
                    amt = _amount(a)   # refuses None
                    pair = canonical_ids.get(twin) if twin is not None and twin not in absorbed else None
                    # The id names the pair; the canonical row must also be a Mission Control call holding the same
                    # reserve (review r4, be2b23f1). Contradictory metadata is not a pair, so the row counts in full.
                    if pair is not None and pair[1] == MC_CALLER and pair[2] == res:
                        absorbed.add(twin)
                        sub += max(0.0, amt - pair[0])
                    else:
                        sub += amt
                    if cid is not None:
                        seen[cid] = (amt, who, res)
                total += sub
                if p == ledgers[0]:
                    canonical_ids = seen
            finally:
                db.close()
        except Exception as e:
            bad.append((p, f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}".strip()))
    return total, bad

def telegram(text):
    """Returns (delivered, detail). Only (True, ...) may be recorded as sent."""
    if DRY:
        return False, "dry-run, not sent"   # never a delivery: must not be recorded as sent
    env = {}
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); env[k] = v.strip().strip('"').strip("'")
    except Exception:
        return False, "no hermes env"
    tok, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_HOME_CHANNEL") or env.get("TELEGRAM_ALERT_CHAT_ID")
    if not tok or not chat:
        return False, "telegram not configured"
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        r = urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
        body = r.read()
    except Exception as e:
        return False, f"send failed: {type(e).__name__}"
    try:
        reply = json.loads(body)
    except ValueError:
        return False, "unparsable response"
    # Telegram answers HTTP 200 with {"ok": false, ...} for some rejections; only ok is True is delivery
    if isinstance(reply, dict) and reply.get("ok") is True:
        return True, "sent"
    return False, str(reply.get("description") or "not ok")[:80] if isinstance(reply, dict) else "unparsable response"

def upsert(d, jid, title, blocker, priority, status="open"):
    j = next((x for x in d["jobs"] if x["id"] == jid), None)
    if j is None:
        d["jobs"].append({"id": jid, "title": title, "owner": "Guardian Jev watcher", "priority": priority,
                          "created": NOW, "updated": NOW, "status": status, "blocker": blocker})
    else:
        j.update({"title": title, "updated": NOW, "status": status, "blocker": blocker, "priority": priority})
    d["updated"] = NOW

def close_row(d, jid):
    j = next((x for x in d["jobs"] if x["id"] == jid), None)
    if j is not None and j["status"] != "done":
        j.update({"status": "done", "updated": NOW, "blocker": ""}); d["updated"] = NOW
        return True
    return False

def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE))
    with os.fdopen(fd, "w") as f:
        json.dump(st, f, allow_nan=False)   # NaN/inf in state is a bug, never a value
    os.replace(tmp, STATE)

def main():
    spent, bad = spent_today()
    try:
        st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    except Exception:
        st = {}
    tg_fail = int(st.get("tg_fail", 0))
    if st.get("day") != DAY:
        st = {"day": DAY, "sent": []}
    rowops, attempted, failed = [], False, False
    for level in (80, 100):
        if spent >= CAP * level / 100 and level not in st["sent"]:
            text = (f"TypeSafe spend today is ${spent:.2f}" + (" or more (some ledgers unreadable)" if bad else "")
                    + f" — {level}% of your ${CAP:.0f} daily cap."
                    + (" New TypeSafe calls stop until the daily reset (10am Brisbane)." if level >= 100 else ""))
            ok, detail = telegram(text)
            if ok:
                attempted = True
                st["sent"].append(level)
            elif not DRY:      # a dry run is not an attempt: it neither records sent nor counts as a delivery failure
                attempted = True
                failed = True
            msg = (f"TypeSafe (Jev) spend ${spent:.2f}{'+' if bad else ''} today (UTC day {DAY}) reached {level}% of ${CAP:.0f}/day cap. "
                   f"Telegram: {detail}{'' if ok else ' (not delivered, will retry)'}")
            rowops.append(lambda d, l=level, m=msg: upsert(d, "W-TYPESAFE-CAP", f"ALERT: {m}", m, "P1" if l >= 100 else "P2"))
            print(NOW, level, f"{spent:.2f}", ok, detail)
    if attempted:
        tg_fail = tg_fail + 1 if failed else 0
    if tg_fail >= 2:
        m = f"Telegram alert delivery has failed {tg_fail} runs in a row; cap alerts are NOT reaching Phill. Check ~/.hermes/.env and network."
        rowops.append(lambda d: upsert(d, "W-ALERT-DELIVERY", f"ALERT: {m}", m, "P1"))
    elif attempted and not failed:
        rowops.append(lambda d: close_row(d, "W-ALERT-DELIVERY"))
    if bad:
        m = (f"Jev spend for UTC day {DAY} is UNKNOWN: lower bound ${spent:.2f} from readable ledgers; unreadable: "
             + "; ".join(f"{p} ({r})" for p, r in bad))
        rowops.append(lambda d: upsert(d, "W-TYPESAFE-CAP-UNKNOWN", f"ALERT: {m}", m, "P2"))
        print(NOW, "UNKNOWN", f"lower bound {spent:.2f}", [p for p, _ in bad])
    else:
        rowops.append(lambda d: close_row(d, "W-TYPESAFE-CAP-UNKNOWN"))

    def _run(d):
        before = json.dumps(d, sort_keys=True)
        for op in rowops:
            op(d)
        return json.dumps(d, sort_keys=True) != before
    jobs_lock.update_jobs(os.path.join(OPS, "jobs.json"), _run)
    st["tg_fail"] = tg_fail
    st["last_spent"] = round(spent, 4); st["last_run"] = NOW
    st["unknown"] = [p for p, _ in bad]
    save_state(st)

if __name__ == "__main__":
    main()
