#!/usr/bin/env python3
"""Tests for jev-cap-watcher.py. Offline: ledgers are temp files, telegram is substituted, HOME is a temp dir.
Run: python3 test_jev_cap_watcher.py"""
import importlib.util, json, os, shutil, sqlite3, sys, tempfile, traceback, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
_n = [0]


def load(tmp, ledgers, cap="20"):
    """ledgers = [spend] or [spend, mission_control]: the watcher's two required ledgers, set through their own
    variables. With one, Mission Control is an empty, healthy ledger so only the given one decides the result."""
    ops = os.path.join(tmp, "ops")
    os.makedirs(ops, exist_ok=True)
    if not os.path.exists(os.path.join(ops, "jobs.json")):
        json.dump({"jobs": [], "updated": ""}, open(os.path.join(ops, "jobs.json"), "w"))
    if len(ledgers) == 1:
        mc = os.path.join(tmp, "mc-empty.sqlite")
        if not os.path.exists(mc):
            sqlite_ledger(mc, "2000-01-01", 0.0)
        ledgers = [ledgers[0], mc]
    os.environ.pop("JEV_WATCH_LEDGERS", None)
    os.environ.update({"HOME": os.path.join(tmp, "home"), "JEV_SPEND_LEDGER": ledgers[0], "JEV_WATCH_MC_LEDGER": ledgers[1],
                       "JEV_WATCH_OPS": ops, "JEV_WATCH_STATE": os.path.join(tmp, "state", "s.json"),
                       "JEV_WATCH_CAP": cap, "JEV_WATCH_SQLITE_TIMEOUT": "0.2"})
    os.environ.pop("JEV_WATCH_DRY", None)
    _n[0] += 1
    spec = importlib.util.spec_from_file_location("jev_cap_%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.OPS == ops
    return mod


def sqlite_ledger(path, day, usd, col="actual_usd"):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE calls (day TEXT, %s REAL, reserved_usd REAL)" % col)
    db.execute("INSERT INTO calls VALUES (?,?,?)", (day, usd, usd))
    db.commit(); db.close()


def rows(tmp):
    return {j["id"]: j for j in json.load(open(os.path.join(tmp, "ops", "jobs.json")))["jobs"]}


def state(tmp):
    return json.load(open(os.path.join(tmp, "state", "s.json")))


def fake_sender(results):
    calls = []

    def send(text):
        calls.append(text)
        return results.pop(0) if results else (True, "sent")
    send.calls = calls
    return send


def good_plus(tmp, bad_path, usd=5.0):
    good = os.path.join(tmp, "good.sqlite")
    return good, [good, bad_path]


def run_with_bad(tmp, make_bad, expect_in_reason=None):
    bad = os.path.join(tmp, "bad.ledger")
    good = os.path.join(tmp, "good.sqlite")
    mod = load(tmp, [good, bad])
    sqlite_ledger(good, mod.DAY, 5.0)
    holder = make_bad(bad)
    mod.telegram = fake_sender([])
    try:
        mod.main()
    finally:
        if holder:
            holder()
    r = rows(tmp)
    assert "W-TYPESAFE-CAP-UNKNOWN" in r, sorted(r)
    msg = r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"]
    assert "lower bound" in msg and "$5.00" in msg and bad in msg, msg
    assert r["W-TYPESAFE-CAP-UNKNOWN"]["status"] == "open"
    assert "W-TYPESAFE-CAP" not in r  # $5 of $20: no cap alert; unknown is its own row
    return mod


def test_healthy_ledgers_sum_and_raise_nothing(tmp):
    a, b = os.path.join(tmp, "a.sqlite"), os.path.join(tmp, "b.sqlite")
    mod = load(tmp, [a, b])
    sqlite_ledger(a, mod.DAY, 5.0)
    sqlite_ledger(b, mod.DAY, 3.0)
    mod.telegram = fake_sender([])
    mod.main()
    assert state(tmp)["last_spent"] == 8.0 and rows(tmp) == {}


def test_missing_ledger_is_unknown_not_zero(tmp):
    run_with_bad(tmp, lambda p: None)


def test_corrupt_sqlite_is_unknown(tmp):
    run_with_bad(tmp, lambda p: open(p, "wb").write(b"this is not a sqlite database at all" * 40) and None)


def _json_at_required_path(tmp, which):
    """Put a well-formed JSON ledger ({DAY: 1.0}) at one required ledger path, a healthy $5 SQLite ledger at the other."""
    good = os.path.join(tmp, "good.sqlite")
    for name in ("ledger.json", "ledger.sqlite"):        # the file name must not decide how it is read
        sub = os.path.join(tmp, which + "-" + name.split(".")[1]); os.makedirs(sub)
        bad = os.path.join(sub, name)
        mod = load(sub, [bad, good] if which == "spend" else [good, bad])
        if not os.path.exists(good):
            sqlite_ledger(good, mod.DAY, 5.0)
        json.dump({mod.DAY: 1.0}, open(bad, "w"))
        mod.telegram = fake_sender([])
        mod.main()
        r = rows(sub)
        assert "W-TYPESAFE-CAP-UNKNOWN" in r, (which, name, r, state(sub))
        msg = r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"]
        assert bad in msg and "$5.00" in msg, (which, name, msg)
        assert state(sub)["last_spent"] == 5.0, (which, name, state(sub))


def test_json_file_at_canonical_ledger_path_is_unknown(tmp):
    # review r4 P1-JSON-ACCEPTED-AS-REQUIRED-SQLITE: a .json file at the canonical ledger path was read as a healthy ledger.
    _json_at_required_path(tmp, "spend")


def test_json_file_at_mission_control_ledger_path_is_unknown(tmp):
    _json_at_required_path(tmp, "mc")


def test_replacement_list_cannot_drop_a_required_ledger(tmp):
    # review r4 P1-REPLACEMENT-LIST-OMITS-REQUIRED-LEDGERS: JEV_WATCH_LEDGERS naming one healthy ledger replaced both
    # required ones, so a missing Mission Control ledger was never looked at and UNKNOWN closed.
    spend, mc = os.path.join(tmp, "spend.sqlite"), os.path.join(tmp, "mc-missing.sqlite")
    mod = load(tmp, [spend, mc])
    sqlite_ledger(spend, mod.DAY, 1.0)
    os.environ["JEV_WATCH_LEDGERS"] = spend
    mod = _reload()
    mod.main()
    r = rows(tmp)
    assert "W-TYPESAFE-CAP-UNKNOWN" in r and mc in r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"], r


def test_ledger_list_variable_is_reported_not_read(tmp):
    # JEV_WATCH_LEDGERS is not a ledger source in any mode: a ledger it names is never summed, and setting it is
    # reported (UNKNOWN), so a leftover override cannot quietly change what the cap counts.
    spend, mc, extra = (os.path.join(tmp, n) for n in ("spend.sqlite", "mc.sqlite", "extra.sqlite"))
    mod = load(tmp, [spend, mc])
    sqlite_ledger(spend, mod.DAY, 1.0); sqlite_ledger(mc, mod.DAY, 2.0); sqlite_ledger(extra, mod.DAY, 100.0)
    os.environ["JEV_WATCH_LEDGERS"] = extra
    mod = _reload()
    mod.main()
    assert state(tmp)["last_spent"] == 3.0, state(tmp)
    r = rows(tmp)
    assert "W-TYPESAFE-CAP-UNKNOWN" in r and "JEV_WATCH_LEDGERS" in r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"], r
    assert "W-TYPESAFE-CAP" not in r, r


def test_both_ledger_variables_naming_one_file_is_unknown(tmp):
    # Pointing both required variables at one file (directly or through a symlink) leaves the Mission Control ledger
    # unread; that is UNKNOWN, and the spend ledger is still counted once as the lower bound.
    spend = os.path.join(tmp, "spend.sqlite")
    link = os.path.join(tmp, "mc-link.sqlite")
    for i, mc in enumerate((spend, link)):
        sub = os.path.join(tmp, "same%d" % i); os.makedirs(sub)
        mod = load(sub, [spend, mc])
        if not os.path.exists(spend):
            sqlite_ledger(spend, mod.DAY, 4.0)
            os.symlink(spend, link)
        mod.telegram = fake_sender([])
        mod.main()
        r = rows(sub)
        assert "W-TYPESAFE-CAP-UNKNOWN" in r and "same file" in r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"], (mc, r)
        assert state(sub)["last_spent"] == 4.0, (mc, state(sub))


def test_uri_characters_in_a_ledger_path_name_that_file(tmp):
    # The path goes into a SQLite URI; unquoted, '?' ended the file name and opened a different file.
    decoy = os.path.join(tmp, "spend.sqlite")
    spend = os.path.join(tmp, "spend.sqlite?mode=rwc")
    mc = os.path.join(tmp, "mc#1.sqlite")
    mod = load(tmp, [spend, mc])
    sqlite_ledger(decoy, mod.DAY, 9.0)
    sqlite_ledger(spend, mod.DAY, 1.0)
    sqlite_ledger(mc, mod.DAY, 2.0)
    total, bad = mod.spent_today()
    assert bad == [] and total == 3.0, (total, bad)


def _reload():
    """Load the watcher again with the environment as it stands (module constants are read at import)."""
    _n[0] += 1
    spec = importlib.util.spec_from_file_location("jev_cap_r%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.telegram = fake_sender([])
    return mod


def test_non_finite_or_negative_spend_is_unknown(tmp):
    # review 26/10: float("NaN") parsed, poisoned the total and was written to state as NaN.
    # SQLite stores a float NaN as NULL, which is refused too; a bool is stored as the integer 1, a real amount.
    for i, raw in enumerate(("NaN", float("nan"), "inf", float("inf"), -1.0, "5x")):
        sub = os.path.join(tmp, "case%d" % i)
        os.makedirs(sub)
        bad = os.path.join(sub, "bad.sqlite")
        good = os.path.join(sub, "good.sqlite")
        mod = load(sub, [good, bad])
        sqlite_ledger(good, mod.DAY, 5.0)
        sqlite_ledger(bad, mod.DAY, raw)
        mod.telegram = fake_sender([])
        mod.main()
        msg = rows(sub)["W-TYPESAFE-CAP-UNKNOWN"]["blocker"]
        assert bad in msg and "$5.00" in msg, (raw, msg)
        assert state(sub)["last_spent"] == 5.0, (raw, state(sub))


def test_negative_sqlite_spend_is_unknown(tmp):
    run_with_bad(tmp, lambda p: sqlite_ledger(p, mod_day(), -3.0))


def test_sqlite_rows_are_checked_one_by_one(tmp):
    # review 26/10 r3: SUM() coerced text to 0 and let +20/-20 cancel, so a bad ledger read
    # as a known $0. Each row must be a finite non-negative number.
    def text_row(p):
        sqlite_ledger(p, mod_day(), 1.0)
        db = sqlite3.connect(p)
        db.execute("INSERT INTO calls VALUES (?,?,?)", (mod_day(), "bogus", None))
        db.commit(); db.close()

    def offsetting(p):
        sqlite_ledger(p, mod_day(), 20.0)
        db = sqlite3.connect(p)
        db.execute("INSERT INTO calls VALUES (?,?,?)", (mod_day(), -20.0, -20.0))
        db.commit(); db.close()
    def null_row(p):
        # review r4: a row with no amount at all was skipped, reading the ledger as a known $0.
        sqlite_ledger(p, mod_day(), 1.0)
        db = sqlite3.connect(p)
        db.execute("INSERT INTO calls VALUES (?,?,?)", (mod_day(), None, None))
        db.commit(); db.close()

    def huge_row(p):
        sqlite_ledger(p, mod_day(), 1e308)
    for i, make in enumerate((text_row, offsetting, null_row, huge_row)):
        sub = os.path.join(tmp, "rows%d" % i)
        os.makedirs(sub)
        run_with_bad(sub, make)


def test_overflowing_ledgers_never_persist_infinity(tmp):
    # review r4: two 1e308 values each passed the finite check and summed to inf, written to
    # state as Infinity. Implausible amounts make the ledger UNKNOWN; state stays valid JSON.
    a, b = os.path.join(tmp, "a.sqlite"), os.path.join(tmp, "b.sqlite")
    mod = load(tmp, [a, b])
    sqlite_ledger(a, mod.DAY, 1e308)
    sqlite_ledger(b, mod.DAY, 1e308)
    mod.telegram = fake_sender([])
    mod.main()
    raw = open(os.path.join(tmp, "state", "s.json")).read()
    assert "Infinity" not in raw and "NaN" not in raw, raw
    assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), rows(tmp)


def mod_day():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def test_locked_sqlite_is_unknown(tmp):
    def lock(p):
        sqlite_ledger(p, "2000-01-01", 1.0)
        c = sqlite3.connect(p, isolation_level=None)
        c.execute("BEGIN EXCLUSIVE")
        return c.close
    run_with_bad(tmp, lock)


def test_renamed_column_is_unknown(tmp):
    run_with_bad(tmp, lambda p: sqlite_ledger(p, "2000-01-01", 1.0, col="spend_usd"))


def test_lower_bound_still_fires_cap_alert_and_unknown_clears_when_fixed(tmp):
    good, missing = os.path.join(tmp, "good.sqlite"), os.path.join(tmp, "later.sqlite")
    mod = load(tmp, [good, missing])
    sqlite_ledger(good, mod.DAY, 25.0)
    mod.telegram = fake_sender([])
    mod.main()
    r = rows(tmp)
    assert r["W-TYPESAFE-CAP"]["status"] == "open" and r["W-TYPESAFE-CAP-UNKNOWN"]["status"] == "open"
    sqlite_ledger(missing, mod.DAY, 1.0)
    mod.main()
    assert rows(tmp)["W-TYPESAFE-CAP-UNKNOWN"]["status"] == "done"


def test_failed_telegram_is_not_recorded_as_sent_and_is_retried(tmp):
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 17.0)
    mod.telegram = fake_sender([(False, "send failed: URLError")])
    mod.main()
    assert state(tmp)["sent"] == [], state(tmp)
    assert rows(tmp)["W-TYPESAFE-CAP"]["status"] == "open"  # the board row is still raised
    mod.telegram = fake_sender([(True, "sent")])
    mod.main()
    assert state(tmp)["sent"] == [80], state(tmp)
    assert len(mod.telegram.calls) == 1


def test_two_consecutive_delivery_failures_raise_w_alert_delivery(tmp):
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 17.0)
    mod.telegram = fake_sender([(False, "no hermes env")] * 5)
    mod.main()
    assert "W-ALERT-DELIVERY" not in rows(tmp)
    mod.main()
    assert rows(tmp)["W-ALERT-DELIVERY"]["status"] == "open"
    mod.telegram = fake_sender([(True, "sent")])
    mod.main()
    assert rows(tmp)["W-ALERT-DELIVERY"]["status"] == "done"
    assert state(tmp)["sent"] == [80]


def test_both_levels_are_tracked_separately_on_partial_failure(tmp):
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 25.0)
    mod.telegram = fake_sender([(True, "sent"), (False, "send failed")])
    mod.main()
    assert state(tmp)["sent"] == [80], state(tmp)


def _hermes_env(tmp):
    d = os.path.join(tmp, "home", ".hermes"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, ".env"), "w").write("TELEGRAM_BOT_TOKEN=dummy-test\nTELEGRAM_HOME_CHANNEL=1\n")


def test_dry_run_is_not_delivery_and_does_not_poison_a_later_live_run(tmp):
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 21.0)
    _hermes_env(tmp)
    mod.DRY = True                      # real telegram(), reaching its dry-run branch
    ok, detail = mod.telegram("x")
    assert ok is False and detail == "dry-run, not sent", (ok, detail)
    mod.main(); mod.main(); mod.main()
    assert state(tmp)["sent"] == [], state(tmp)
    assert "W-ALERT-DELIVERY" not in rows(tmp), rows(tmp)
    mod.DRY = False
    mod.telegram = fake_sender([])
    mod.main()
    assert state(tmp)["sent"] == [80, 100], state(tmp)
    assert len(mod.telegram.calls) == 2


def test_dry_run_without_hermes_env_is_still_not_a_delivery_failure(tmp):
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 21.0)
    mod.DRY = True
    mod.main(); mod.main(); mod.main()
    assert state(tmp)["sent"] == [] and "W-ALERT-DELIVERY" not in rows(tmp), (state(tmp), rows(tmp))


class _Resp:
    def __init__(self, body):
        self.body = body
        self.status = 200

    def read(self, *a):
        return self.body


def _with_urlopen(mod, body):
    import urllib.request
    real = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: _Resp(body)
    return real


def _real_telegram_run(tmp, body):
    """Run the REAL telegram() through main() against an HTTP 200 carrying `body`; return (state, mod)."""
    import urllib.request
    led = os.path.join(tmp, "l.sqlite")
    mod = load(tmp, [led])
    sqlite_ledger(led, mod.DAY, 17.0)
    _hermes_env(tmp)
    real = _with_urlopen(mod, body)
    try:
        mod.main()
    finally:
        urllib.request.urlopen = real
    return mod


def test_telegram_ok_false_body_is_not_sent_and_is_retried(tmp):
    import urllib.request
    mod = _real_telegram_run(tmp, b'{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}')
    assert state(tmp)["sent"] == [], state(tmp)
    assert "chat not found" in rows(tmp)["W-TYPESAFE-CAP"]["blocker"], rows(tmp)
    real = _with_urlopen(mod, b'{"ok":true,"result":{}}')
    try:
        mod.main()
    finally:
        urllib.request.urlopen = real
    assert state(tmp)["sent"] == [80], state(tmp)


def test_telegram_non_json_body_is_not_sent(tmp):
    mod = _real_telegram_run(tmp, b"<html>gateway</html>")
    assert state(tmp)["sent"] == [], state(tmp)
    assert "unparsable response" in rows(tmp)["W-TYPESAFE-CAP"]["blocker"], rows(tmp)


def test_telegram_ok_must_be_literally_true(tmp):
    for body in (b'{"ok":"true"}', b'{"ok":1}', b'[]', b'{}'):
        d = tempfile.mkdtemp(prefix="jevcap-test-", dir=tmp)
        _real_telegram_run(d, body)
        assert state(d)["sent"] == [], (body, state(d))


def test_telegram_ok_true_is_sent(tmp):
    _real_telegram_run(tmp, b'{"ok":true,"result":{"message_id":1}}')
    assert state(tmp)["sent"] == [80], state(tmp)


def test_default_ledgers_include_mission_control(tmp):
    # The installed copy carried this ledger while the library did not, so a reinstall dropped it.
    os.environ.pop("JEV_WATCH_LEDGERS", None)
    os.environ["HOME"] = os.path.join(tmp, "home")
    spec = importlib.util.spec_from_file_location("jev_cap_default", os.path.join(SCRIPTS, "jev-cap-watcher.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "/Volumes/Mini Mini 2T Storage/ops/jev/mission-control-jev-ledger.sqlite" in mod.LEDGERS, mod.LEDGERS


# --- canonical spend ledger (RA-8116 / UNI-3074 W4) -------------------------------------------------
SPEND_SCHEMA = ("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, caller TEXT NOT NULL, "
                "reserved_usd REAL NOT NULL, actual_usd REAL, input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, "
                "call_id TEXT)")   # call_id: Pi-Dev-Ops RA-8116 (PR #956), a random id never reused after a reset


MC = "mission_control_jev_shadow"   # the caller name Pi-Dev-Ops writes for Mission Control rows in the spend ledger


def spend_ledger(path, rows, legacy=False):
    """rows: (day, reserved, actual-or-None, status[, caller[, call_id]]). Same schema as Pi-Dev-Ops jev_platform/spend.py;
    a row with no call_id given gets a fresh random one, as spend.reserve_call does. legacy=True: the schema before call_id."""
    db = sqlite3.connect(path)
    db.execute(SPEND_SCHEMA.split(", call_id TEXT")[0] + ")" if legacy else SPEND_SCHEMA)
    for day, reserved, actual, status, *rest in rows:
        who = rest[0] if rest else "test"
        cid = rest[1] if len(rest) > 1 else uuid.uuid4().hex
        if legacy:
            db.execute("INSERT INTO calls(day, caller, reserved_usd, actual_usd, status, created_at) VALUES (?,?,?,?,?,?)",
                       (day, who, reserved, actual, status, day + "T00:00:00+00:00"))
        else:
            db.execute("INSERT INTO calls(day, caller, reserved_usd, actual_usd, status, created_at, call_id) VALUES (?,?,?,?,?,?,?)",
                       (day, who, reserved, actual, status, day + "T00:00:00+00:00", cid))
    db.commit(); db.close()


def load_default(tmp, spend=None, mc=None):
    """Load the watcher with its DEFAULT ledger list: no JEV_WATCH_LEDGERS, spend ledger via JEV_SPEND_LEDGER."""
    ops = os.path.join(tmp, "ops")
    os.makedirs(ops, exist_ok=True)
    if not os.path.exists(os.path.join(ops, "jobs.json")):
        json.dump({"jobs": [], "updated": ""}, open(os.path.join(ops, "jobs.json"), "w"))
    os.environ.pop("JEV_WATCH_LEDGERS", None)
    os.environ.update({"HOME": os.path.join(tmp, "home"), "JEV_WATCH_OPS": ops,
                       "JEV_WATCH_STATE": os.path.join(tmp, "state", "s.json"), "JEV_WATCH_CAP": "20",
                       "JEV_WATCH_SQLITE_TIMEOUT": "0.2",
                       "JEV_WATCH_MC_LEDGER": mc or os.path.join(tmp, "no-mc.sqlite")})
    os.environ["JEV_SPEND_LEDGER"] = spend or os.path.join(tmp, "spend.sqlite")
    _n[0] += 1
    spec = importlib.util.spec_from_file_location("jev_cap_d%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.telegram = fake_sender([])
    return mod


def _mc_ledger(path, rows):
    """Mission Control shadow ledger: old table plus the nullable spend_id (PR #955) and spend_call_id (PR #956) columns.
    rows: (day, reserved, actual, spend_call_id-or-None). spend_id is the canonical row number, which a reset reuses,
    so every mirror row here carries spend_id 1 to prove the watcher never pairs by it. No unique index on
    spend_call_id: the watcher must not rely on one."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, reserved_usd REAL NOT NULL, actual_usd REAL, "
               "input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, spend_id INTEGER, spend_call_id TEXT)")
    for day, reserved, actual, link in rows:
        db.execute("INSERT INTO calls(day, reserved_usd, actual_usd, status, created_at, spend_id, spend_call_id) "
                   "VALUES (?,?,?,?,?,?,?)", (day, reserved, actual, "answered", day, 1, link))
    db.commit(); db.close()


def test_canonical_ledger_sums_answered_and_attempted_rows(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    mc = os.path.join(tmp, "mc.sqlite"); _mc_ledger(mc, [])
    mod = load_default(tmp, spend=spend, mc=mc)
    spend_ledger(spend, [(mod.DAY, 0.02, 0.01, "answered"), (mod.DAY, 0.0027, None, "attempted")])
    total, bad = mod.spent_today()
    assert bad == [], bad
    assert abs(total - 0.0127) < 1e-9, total
    mod.main()
    assert rows(tmp) == {} and state(tmp)["last_spent"] == 0.0127 and state(tmp)["unknown"] == [], (rows(tmp), state(tmp))


def test_canonical_ledger_missing_is_unknown(tmp):
    mc = os.path.join(tmp, "mc.sqlite"); _mc_ledger(mc, [])
    mod = load_default(tmp, mc=mc)
    mod.main()
    r = rows(tmp)
    assert "W-TYPESAFE-CAP-UNKNOWN" in r and os.path.join(tmp, "spend.sqlite") in r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"], r
    assert "missing" in r["W-TYPESAFE-CAP-UNKNOWN"]["blocker"]


def test_canonical_ledger_without_calls_table_is_unknown(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    db = sqlite3.connect(spend); db.execute("CREATE TABLE other (x INTEGER)"); db.commit(); db.close()
    mc = os.path.join(tmp, "mc.sqlite"); _mc_ledger(mc, [])
    mod = load_default(tmp, spend=spend, mc=mc)
    mod.main()
    assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp) and spend in rows(tmp)["W-TYPESAFE-CAP-UNKNOWN"]["blocker"], rows(tmp)


def test_blank_or_relative_mission_control_override_keeps_unknown_open(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    spend_ledger(spend, [])
    corrupt = os.path.join(tmp, "mc-corrupt.sqlite")
    open(corrupt, "w").write("not sqlite")
    load_default(tmp, spend=spend, mc=corrupt).main()
    assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), rows(tmp)
    for bad in ("", "   ", "relative/mc.sqlite"):
        load_default(tmp, spend=spend)  # sets every other env var
        os.environ["JEV_WATCH_MC_LEDGER"] = bad
        _n[0] += 1
        spec = importlib.util.spec_from_file_location("jev_cap_b%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.telegram = fake_sender([])
        total, unreadable = mod.spent_today()
        assert unreadable, (bad, total, mod.LEDGERS)
        mod.main()
        assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), (bad, rows(tmp))


def test_blank_or_relative_ledger_list_items_keep_unknown_open(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    spend_ledger(spend, [])
    corrupt = os.path.join(tmp, "mc-corrupt.sqlite")
    open(corrupt, "w").write("not sqlite")
    load_default(tmp, spend=spend, mc=corrupt).main()
    assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), rows(tmp)
    for bad in ("", ":", "   ", spend + ":", ":" + spend, spend + "::" + spend, "relative/x.sqlite", spend + ":rel.sqlite"):
        load_default(tmp, spend=spend)  # sets every other env var
        os.environ["JEV_WATCH_LEDGERS"] = bad
        _n[0] += 1
        spec = importlib.util.spec_from_file_location("jev_cap_l%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.telegram = fake_sender([])
        total, unreadable = mod.spent_today()
        assert unreadable, (bad, total, mod.LEDGERS)
        mod.main()
        assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), (bad, rows(tmp))
    os.environ.pop("JEV_WATCH_LEDGERS", None)


def test_rejected_overrides_never_read_a_file_named_like_them(tmp):
    """A rejected override must not become a filename: plant a readable, empty ledger under every name the old
    sentinel used (and under the raw relative value) in the working directory; UNKNOWN must stay open."""
    spend = os.path.join(tmp, "spend.sqlite")
    spend_ledger(spend, [])
    corrupt = os.path.join(tmp, "mc-corrupt.sqlite")
    open(corrupt, "w").write("not sqlite")
    good_mc = os.path.join(tmp, "mc-good.sqlite"); _mc_ledger(good_mc, [])  # so only the rejected input can fail
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        cases = [("JEV_SPEND_LEDGER", ""), ("JEV_SPEND_LEDGER", "rel.sqlite"),
                 ("JEV_WATCH_MC_LEDGER", ""), ("JEV_WATCH_MC_LEDGER", "rel.sqlite"),
                 ("JEV_WATCH_LEDGERS", ""), ("JEV_WATCH_LEDGERS", "rel.sqlite")]
        for var, raw in cases:
            for name in ("%s-unusable[%s]" % (var, raw), raw):
                if name and not os.path.exists(os.path.join(tmp, name)):
                    spend_ledger(os.path.join(tmp, name), [])
            load_default(tmp, spend=spend, mc=corrupt).main()   # opens UNKNOWN
            assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), rows(tmp)
            load_default(tmp, spend=spend, mc=good_mc)
            os.environ[var] = raw
            _n[0] += 1
            spec = importlib.util.spec_from_file_location("jev_cap_s%d" % _n[0], os.path.join(SCRIPTS, "jev-cap-watcher.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.telegram = fake_sender([])
            total, unreadable = mod.spent_today()
            assert unreadable, (var, raw, total, mod.LEDGERS)
            mod.main()
            assert "W-TYPESAFE-CAP-UNKNOWN" in rows(tmp), (var, raw, rows(tmp))
            os.environ.pop("JEV_WATCH_LEDGERS", None)
    finally:
        os.chdir(cwd)


def test_canonical_ledger_excludes_other_days(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    mc = os.path.join(tmp, "mc.sqlite"); _mc_ledger(mc, [])
    mod = load_default(tmp, spend=spend, mc=mc)
    spend_ledger(spend, [("2000-01-01", 5.0, 5.0, "answered"), (mod.DAY, 0.5, 0.25, "answered")])
    total, bad = mod.spent_today()
    assert bad == [] and abs(total - 0.25) < 1e-9, (total, bad)


def test_canonical_ledger_bad_amounts_are_unknown(tmp):
    # reserved_usd is NOT NULL in the real schema, so a bad amount needs a ledger with a loosened column; actual_usd can be anything.
    for i, (reserved, actual) in enumerate(((1.0, float("inf")), (-1.0, None), (1.0, -2.0), (1.0, "x"))):
        sub = os.path.join(tmp, "amt%d" % i); os.makedirs(sub)
        spend = os.path.join(sub, "spend.sqlite")
        mc = os.path.join(sub, "mc.sqlite"); _mc_ledger(mc, [])
        mod = load_default(sub, spend=spend, mc=mc)
        db = sqlite3.connect(spend); db.execute(SPEND_SCHEMA)
        db.execute("INSERT INTO calls(day, caller, reserved_usd, actual_usd, status, created_at) VALUES (?,?,?,?,?,?)",
                   (mod.DAY, "t", reserved, actual, "x", "x"))
        db.commit(); db.close()
        total, bad = mod.spent_today()
        assert any(p == spend for p, _ in bad), (reserved, actual, bad)


def test_default_ledgers_name_no_relint_path_and_never_open_one(tmp):
    spend = os.path.join(tmp, "spend.sqlite")
    mod = load_default(tmp, spend=spend)
    spend_ledger(spend, [(mod.DAY, 0.1, 0.1, "answered")])
    assert not any("relint" in p for p in mod.LEDGERS), mod.LEDGERS
    touched = []
    real_exists, real_connect = os.path.exists, sqlite3.connect
    os.path.exists = lambda p, *a: (touched.append(str(p)), real_exists(p))[1]
    sqlite3.connect = lambda p, *a, **k: (touched.append(str(p)), real_connect(p, *a, **k))[1]
    try:
        mod.spent_today()
    finally:
        os.path.exists, sqlite3.connect = real_exists, real_connect
    assert touched and not any("relint" in p for p in touched), touched
    os.environ.pop("JEV_SPEND_LEDGER")           # default path too: ~/.local/state/jev/spend.sqlite under HOME
    os.environ.pop("JEV_WATCH_MC_LEDGER")
    spec = importlib.util.spec_from_file_location("jev_cap_nr", os.path.join(SCRIPTS, "jev-cap-watcher.py"))
    m2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(m2)
    assert os.path.join(tmp, "home", ".local/state/jev/spend.sqlite") in m2.LEDGERS, m2.LEDGERS
    assert not any("relint" in p for p in m2.LEDGERS), m2.LEDGERS


def test_mission_control_calls_mirrored_into_spend_ledger_count_once(tmp):
    spend = os.path.join(tmp, "spend.sqlite"); mc = os.path.join(tmp, "mc.sqlite")
    mod = load_default(tmp, spend=spend, mc=mc)
    # canonical: one MC call (call A, settled 0.01) and one other caller (0.0027 attempted)
    spend_ledger(spend, [(mod.DAY, 0.02, 0.01, "answered", MC, "A"), (mod.DAY, 0.0027, None, "attempted")])
    # MC ledger: the mirrored copy of call A, plus one call that never reached the canonical ledger (NULL)
    _mc_ledger(mc, [(mod.DAY, 0.02, 0.01, "A"), (mod.DAY, 0.5, 0.5, None)])
    total, bad = mod.spent_today()
    assert bad == [] and abs(total - (0.0127 + 0.5)) < 1e-9, (total, bad)


def test_mission_control_row_is_paired_only_by_a_call_id_in_todays_canonical_ledger(tmp):
    # review r1 (48aba1f6): an orphaned mirror read as a known $0. review r3 (d191f9cf): after a canonical reset, row
    # number, caller and reserve all repeat, so a different call was paired with an old mirror and $4 + $2 read as $4.
    # canon rows: (day, reserved, actual, call_id[, caller]); mc rows: (actual, spend_call_id), reserved 18.
    # legacy: canonical has no call_id.
    cases = (
        ("orphan call id, canonical empty", [], [(18.0, "A")], 18.0, False, False),
        ("call id of another day's row", [("2000-01-01", 18.0, 18.0, "A")], [(18.0, "A")], 18.0, False, False),
        ("matching call id today", [(None, 18.0, 18.0, "A")], [(18.0, "A")], 18.0, False, False),
        ("reset: new call B reuses row 1, old mirror A", [(None, 18.0, 2.0, "B")], [(4.0, "A")], 6.0, False, False),
        ("reset, new call mirrored too", [(None, 18.0, 2.0, "B")], [(4.0, "A"), (1.0, "B")], 6.0, False, False),
        ("canonical written before call ids", [(None, 18.0, 18.0, None)], [(18.0, "A")], 36.0, False, True),
        ("canonical unreadable", None, [(18.0, "A")], 18.0, True, False),
        # review r4 (be2b23f1): the id alone is not enough; caller and reserve must agree too, else both count
        ("call id names a non-Mission-Control call", [(None, 18.0, 10.0, "A", "skill_router")], [(4.0, "A")], 14.0, False, False),
        ("call id names a call with another reserve", [(None, 9.0, 10.0, "A")], [(4.0, "A")], 14.0, False, False),
    )
    for i, (name, canon, mc_rows, want, unknown, legacy) in enumerate(cases):
        sub = os.path.join(tmp, "mirror%d" % i); os.makedirs(sub)
        spend, mc = os.path.join(sub, "spend.sqlite"), os.path.join(sub, "mc.sqlite")
        mod = load_default(sub, spend=spend, mc=mc)
        if canon is None:
            open(spend, "w").write("not sqlite")
        else:
            spend_ledger(spend, [(d or mod.DAY, r, a, "answered", (who or [MC])[0], cid) for d, r, a, cid, *who in canon],
                         legacy=legacy)
        _mc_ledger(mc, [(mod.DAY, 18.0, a, link) for a, link in mc_rows])
        mod.main()
        assert abs(state(sub)["last_spent"] - want) < 1e-9, (name, state(sub))
        assert ("W-TYPESAFE-CAP-UNKNOWN" in rows(sub)) is unknown, (name, rows(sub))


def _mirror_pair(tmp, canon_actual, mc_actual, extra_mc=()):
    """Canonical call A is a Mission Control call reserved at 18.0; MC row(s) mirror it with spend_call_id A."""
    spend = os.path.join(tmp, "spend.sqlite"); mc = os.path.join(tmp, "mc.sqlite")
    mod = load_default(tmp, spend=spend, mc=mc)
    spend_ledger(spend, [(mod.DAY, 18.0, canon_actual, "answered", MC, "A")])
    _mc_ledger(mc, [(mod.DAY, 18.0, mc_actual, "A")] + [(mod.DAY, r, a, s) for r, a, s in extra_mc])
    return mod


def test_matched_mirror_row_with_invalid_amount_is_unknown(tmp):
    # review r2 (d5eb03fa): a matched mirror row was skipped before _amount ran, so a bad amount on it was never seen
    for i, bad_amount in enumerate((-5.0, float("inf"), "twelve", 2e6)):   # SQLite stores NaN as NULL (falls back to the reserve)
        sub = os.path.join(tmp, "bad%d" % i); os.makedirs(sub)
        mod = _mirror_pair(sub, 1.0, bad_amount)
        total, bad = mod.spent_today()
        assert any(p == mod.MC_LEDGER for p, _ in bad), (bad_amount, total, bad)


def test_matched_mirror_pair_counts_the_larger_amount(tmp):
    # review r2 (d5eb03fa): canonical settled $1, Mission Control settled $18 for the same call; $1 was counted
    for i, (canon, mirror, want) in enumerate(((1.0, 18.0, 18.0), (18.0, 1.0, 18.0), (5.0, 5.0, 5.0), (None, 3.0, 18.0))):
        sub = os.path.join(tmp, "pair%d" % i); os.makedirs(sub)
        mod = _mirror_pair(sub, canon, mirror)
        total, bad = mod.spent_today()
        assert bad == [] and abs(total - want) < 1e-9, ((canon, mirror), total, bad)


def test_one_canonical_row_absorbs_at_most_one_mirror_row(tmp):
    # two Mission Control rows naming the same canonical call are two charges; at most one is the mirrored copy
    mod = _mirror_pair(tmp, 18.0, 18.0, extra_mc=[(18.0, 18.0, "A")])
    total, bad = mod.spent_today()
    assert bad == [] and abs(total - 36.0) < 1e-9, (total, bad)


def test_canonical_ledger_failing_part_way_leaves_no_ids_to_discount_against(tmp):
    # call A is good, the next row is bad: the canonical ledger is UNKNOWN and counted as $0, so its mirror counts in full
    spend = os.path.join(tmp, "spend.sqlite"); mc = os.path.join(tmp, "mc.sqlite")
    mod = load_default(tmp, spend=spend, mc=mc)
    spend_ledger(spend, [(mod.DAY, 18.0, 18.0, "answered", MC, "A"), (mod.DAY, 1.0, -1.0, "answered")])
    _mc_ledger(mc, [(mod.DAY, 18.0, 18.0, "A")])
    total, bad = mod.spent_today()
    assert [p for p, _ in bad] == [spend] and abs(total - 18.0) < 1e-9, (total, bad)


def test_old_mission_control_ledger_without_spend_id_still_counts(tmp):
    spend = os.path.join(tmp, "spend.sqlite"); mc = os.path.join(tmp, "mc.sqlite")
    mod = load_default(tmp, spend=spend, mc=mc)
    spend_ledger(spend, [(mod.DAY, 0.1, 0.1, "answered")])
    sqlite_ledger(mc, mod.DAY, 0.4)              # no spend_id column: un-migrated, never UNKNOWN
    total, bad = mod.spent_today()
    assert bad == [] and abs(total - 0.5) < 1e-9, (total, bad)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    env, failed = dict(os.environ), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="jevcap-test-")
        try:
            fn(tmp)
            print("PASS " + name)
        except BaseException:  # noqa: BLE001
            failed += 1
            print("FAIL %s\n%s" % (name, traceback.format_exc()))
        finally:
            os.environ.clear(); os.environ.update(env)
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
