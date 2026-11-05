"""Ops Board usage board: one row per account, from ACCOUNT-MAP + HEADROOM (RA-8190, AR-04).

Reads the account map (ops/ACCOUNT-MAP.yaml, AR-01) and the HEADROOM log (AR-02) and
prints what Phill's Ops Board shows: per account its label, provider, plan, machine
pins, state, last limit event and reset (AEST), active/queued jobs, 7-day job-hours and
usage. It raises alerts for a mis-pin, two machines sharing one Claude email, and an
account over 80% of a known usage window.

It only reads. It never signs in or out, switches accounts, reads a credential or
decides to spend. Emails are compared in memory and never printed; every printed value
is a checked id, a number or a fixed string, never log text. A map or log it cannot
read is a failure (exit 2 / 3), never a quiet board. A column with no source is null.

    python3 scripts/account_board.py [--map ops/ACCOUNT-MAP.yaml] [--log PATH]
        [--jobs FILE] [--job-hours FILE] [--usage FILE] [--format json|md] [--now ISO]

Exit: 0 no alerts, 1 alerts raised (the hook), 2 bad map/tables/arguments, 3 log unreadable.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account_picker import (
    _ID,
    DEFAULT_LOG,
    DEFAULT_MAP,
    RESET_TRUSTED,
    InputError,
    LogUnknown,
    _UniqueKeyLoader,
    _when,
    hold_until,
    read_log,
)

AEST = ZoneInfo("Australia/Brisbane")  # AEST all year, no daylight saving
HIGH_USAGE_PCT = 80
PROVIDERS = ("claude", "codex", "cursor")
COLUMNS = ("label", "provider", "plan", "machines", "state", "last_event", "reset_at",
           "active_jobs", "queued_jobs", "job_hours_7d", "usage_pct")

__all__ = ["InputError", "LogUnknown", "build", "load_accounts", "load_number_table", "main"]


def _aest(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(epoch, AEST).strftime("%Y-%m-%d %H:%M AEST")
    except (ValueError, OverflowError, OSError):
        return "far-future"


def _ok_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.match(value))


def _account(a: object, machines: list) -> dict:
    if not isinstance(a, dict) or not _ok_id(a.get("label")) or a.get("provider") not in PROVIDERS \
            or not isinstance(a.get("machines"), list) or not all(_ok_id(m) for m in a["machines"]):
        raise InputError("account map has a malformed account")
    plan, email = a.get("plan"), a.get("email")
    if plan is not None and not _ok_id(plan):
        raise InputError("account map has a malformed plan")
    key = email.strip().lower() if isinstance(email, str) and email.strip() else None
    return {"label": a["label"], "provider": a["provider"], "plan": plan,
            "machines": sorted(m for m in set(a["machines"]) if m in machines), "_email": key}


def load_accounts(path: str | Path) -> dict:
    """Machine ids and accounts. The email is kept only as a private compare key."""
    try:
        doc = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InputError(f"account map unreadable: {type(exc).__name__}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("machines"), list) \
            or not isinstance(doc.get("accounts"), list):
        raise InputError("account map needs 'machines' and 'accounts' lists")
    machines = [m.get("id") if isinstance(m, dict) else None for m in doc["machines"]]
    if not machines or not all(_ok_id(m) for m in machines):
        raise InputError("account map has a missing or malformed machine id")
    accounts = [_account(a, machines) for a in doc["accounts"]]
    if len({a["label"] for a in accounts}) != len(accounts):
        raise InputError("account map repeats an account label")
    return {"machines": machines, "accounts": accounts}


def _hold(acct: dict, events: list, now: float) -> dict:
    mine = [r for r in events if r["provider"] == acct["provider"] and r["machine"] in acct["machines"]]
    out = {"state": "green", "last_event": None, "reset_at": None, "reset_source": None}
    if not mine:
        return out
    last = max(mine, key=lambda r: _when(r["ts"]))
    out["last_event"] = {"event": last["event"], "at": _aest(_when(last["ts"])), "machine": last["machine"]}
    held = max(mine, key=hold_until)
    until = hold_until(held)
    if until > now:
        printed = held["event"] in RESET_TRUSTED and _when(held.get("reset_at")) == until
        out.update(state=held["event"], reset_at=_aest(until),
                   reset_source="printed" if printed else "fallback")
    return out


def _sum(table: dict | None, machines: list, key: str | None = None) -> float | None:
    """Total over the account's machines; null unless every machine is in the table."""
    if table is None or not machines or not all(m in table for m in machines):
        return None
    vals = [table[m] if key is None else table[m].get(key) for m in machines]
    return None if any(v is None for v in vals) else sum(vals)


def _row(acct: dict, events: list, now: float, jobs: dict | None, hours: dict | None,
         usage: dict | None) -> dict:
    ms = acct["machines"]
    return {"label": acct["label"], "provider": acct["provider"], "plan": acct["plan"], "machines": ms,
            **_hold(acct, events, now),
            "active_jobs": _sum(jobs, ms, "active"), "queued_jobs": _sum(jobs, ms, "queued"),
            "job_hours_7d": _sum(hours, ms), "usage_pct": (usage or {}).get(acct["label"])}


def _pin_alerts(amap: dict) -> list:
    out = []
    for m in amap["machines"]:
        for p in PROVIDERS:
            n = sum(1 for a in amap["accounts"] if a["provider"] == p and m in a["machines"])
            if n > 1 or (p == "claude" and n == 0):  # every machine needs exactly one Claude seat
                out.append({"kind": "mis_pin", "machine": m, "provider": p, "pins": n})
    return out


def _email_alerts(amap: dict) -> list:
    groups: dict = {}
    for a in amap["accounts"]:
        if a["provider"] == "claude" and a["_email"]:
            groups.setdefault(a["_email"], []).append(a)
    out = []
    for accts in groups.values():
        machines = sorted({m for a in accts for m in a["machines"]})
        if len(machines) > 1:
            out.append({"kind": "shared_claude_email", "accounts": sorted(a["label"] for a in accts),
                        "machines": machines})
    return sorted(out, key=lambda x: x["accounts"])


def build(amap: dict, events: list, *, now: float, jobs: dict | None = None,
          hours: dict | None = None, usage: dict | None = None) -> dict:
    """Board rows, alerts and a per-check status (ok / alert / UNKNOWN). Pure."""
    rows = [_row(a, events, now, jobs, hours, usage) for a in amap["accounts"]]
    high = [{"kind": "high_usage", "account": r["label"], "pct": r["usage_pct"]}
            for r in rows if r["usage_pct"] is not None and r["usage_pct"] > HIGH_USAGE_PCT]
    pins, emails = _pin_alerts(amap), _email_alerts(amap)
    usage_known = all(r["usage_pct"] is not None for r in rows)
    checks = {"mis_pin": "alert" if pins else "ok", "shared_claude_email": "alert" if emails else "ok",
              "high_usage": "alert" if high else ("ok" if usage_known else "UNKNOWN")}
    return {"now": _aest(now), "rows": rows, "alerts": pins + emails + high, "checks": checks}


def _num(v: object) -> bool:
    try:  # math.isfinite raises OverflowError on an int beyond float range
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
    except OverflowError:
        return False


def load_number_table(path: str | Path | None, nested: tuple = ()) -> dict | None:
    """{id: number} (or {id: {field: number}} for `nested` fields). None when not given."""
    if path is None:
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(f"table unreadable: {type(exc).__name__}") from None
    if not isinstance(doc, dict) or not all(_ok_id(k) for k in doc):
        raise InputError("table must be a JSON object keyed by id")
    vals = [x for v in doc.values() for x in ([v.get(f) for f in nested] if nested and isinstance(v, dict)
                                              else [v if not nested else None])]
    if not all(_num(x) for x in vals):
        raise InputError("table values must be non-negative numbers")
    return doc


def to_markdown(board: dict) -> str:
    def cell(v: object) -> str:
        if v is None:
            return "-"
        if isinstance(v, dict):
            return f"{v['event']} {v['at']}"
        return ", ".join(v) if isinstance(v, list) else str(v)
    lines = [f"Account board, {board['now']}", "", "| " + " | ".join(COLUMNS) + " |",
             "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(cell(r[c]) for c in COLUMNS) + " |" for r in board["rows"]]
    lines += ["", "Checks: " + ", ".join(f"{k} {v}" for k, v in board["checks"].items())]
    lines += [f"ALERT {json.dumps(a, sort_keys=True)}" for a in board["alerts"]]
    return "\n".join(lines)


def _args(argv: list | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--map", default=str(DEFAULT_MAP))
    p.add_argument("--log", default=os.environ.get("HEADROOM_LOG") or DEFAULT_LOG)
    p.add_argument("--jobs", help='JSON: machine id -> {"active": n, "queued": n}')
    p.add_argument("--job-hours", help="JSON: machine id -> job-hours in the last 7 days")
    p.add_argument("--usage", help="JSON: account label -> percent of its known usage window")
    p.add_argument("--format", choices=("json", "md"), default="json")
    p.add_argument("--now", help="ISO time to report at (default: now)")
    return p.parse_args(argv)


def main(argv: list | None = None) -> int:
    a = _args(argv)
    now = _when(a.now) if a.now else datetime.now(UTC).timestamp()
    try:
        if now is None:
            raise InputError("--now is not an ISO time")
        amap = load_accounts(a.map)
        tables = {"jobs": load_number_table(a.jobs, ("active", "queued")),
                  "hours": load_number_table(a.job_hours), "usage": load_number_table(a.usage)}
        log = read_log(a.log)
    except InputError as exc:
        print(f"account-board: {exc}", file=sys.stderr)
        return 2
    except LogUnknown as exc:
        print(f"account-board: UNKNOWN, no board: {exc}", file=sys.stderr)
        return 3
    board = build(amap, log["events"], now=now, **tables)
    board["log"] = {"status": log["status"], "events": len(log["events"]), "malformed": log["malformed"]}
    print(to_markdown(board) if a.format == "md" else json.dumps(board, indent=2))
    return 1 if board["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())
