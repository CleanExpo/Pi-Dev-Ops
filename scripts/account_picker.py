"""Night-queue picker: which machine gets the next job (RA-8189, AR-03).

Reads the account map (ops/ACCOUNT-MAP.yaml, AR-01) and the HEADROOM log (AR-02) and
answers one question: which candidate machine should run the next job for a provider?
A machine whose pinned account is cooling is skipped; among the rest, a Max seat with no
recent limit event and the fewest job-hours wins.

It only chooses. It never claims a job, signs in or out, switches accounts, reads a
credential, or decides to spend. It never prints an email, and every reason it prints is
built from fixed strings, never from log text. A log it cannot read is UNKNOWN (exit 3),
never a quiet night.

    python3 scripts/account_picker.py [--provider claude] [--machines mini,macbook]
        [--map ops/ACCOUNT-MAP.yaml] [--log PATH] [--job-hours FILE] [--now ISO]

Exit: 0 picked, 1 nothing eligible, 2 bad map/arguments, 3 HEADROOM log unreadable.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

SCHEMA = "headroom/1"
DEFAULT_LOG = "/Volumes/Mini Mini 2T Storage/ops/headroom/headroom-events.jsonl"  # AR-02 default
DEFAULT_MAP = Path(__file__).resolve().parent.parent / "ops" / "ACCOUNT-MAP.yaml"
H = 3600.0
# A window with a printed reset holds until it; otherwise for the fallback below. A dead
# login, blocked plan or spend cap needs a person: retried at most once per 12 hours.
FALLBACK_HOLD_S = {"5h_cooling": 5 * H, "weekly_cooling": 24 * H, "auth_expired": 12 * H,
                   "billing_blocked": 12 * H, "on_demand_capped": 12 * H}
RESET_TRUSTED = ("5h_cooling", "weekly_cooling")
MAX_RESET_S = 8 * 24 * H  # a weekly limit resets within a week; later is a misread
RECENT_S = 7 * 24 * H     # a limit event this recent makes a seat "recovered", not "green"
TOLERANCE = 0.2           # evenness target: each Max seat within +-20% of the mean
_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


class InputError(Exception):
    """The map, job-hours table or arguments are unusable (exit 2)."""


class LogUnknown(Exception):
    """The HEADROOM log could not be read; its state is unknown (exit 3)."""


def _when(value) -> Optional[float]:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def _iso(epoch: float) -> str:
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):  # past year 9999: still a hold, never a crash
        return "far-future"


def load_map(path) -> dict:
    """Machine ids and, per account, provider / Max flag / machines. Emails are dropped."""
    try:
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InputError(f"account map unreadable: {type(exc).__name__}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("machines"), list) \
            or not isinstance(doc.get("accounts"), list):
        raise InputError("account map needs 'machines' and 'accounts' lists")
    machines = [m.get("id") if isinstance(m, dict) else None for m in doc["machines"]]
    if not machines or not all(isinstance(m, str) and _ID.match(m) for m in machines):
        raise InputError("account map has a missing or malformed machine id")
    accounts = []
    for a in doc["accounts"]:
        if not isinstance(a, dict) or not isinstance(a.get("provider"), str) \
                or not isinstance(a.get("machines"), list):
            raise InputError("account map has a malformed account")
        accounts.append({"provider": a["provider"], "max": a.get("plan") == "max",
                         "machines": [m for m in a["machines"] if m in machines]})
    return {"machines": machines, "accounts": accounts}


def _valid(r) -> bool:
    return (isinstance(r, dict) and r.get("schema") == SCHEMA and r.get("event") in FALLBACK_HOLD_S
            and isinstance(r.get("machine"), str) and isinstance(r.get("provider"), str)
            and _when(r.get("ts")) is not None
            and (r.get("reset_at") is None or _when(r.get("reset_at")) is not None))


def read_log(path) -> dict:
    """Valid records and a count of lines that could not be trusted. Unreadable: LogUnknown."""
    path = Path(path)
    if not path.parent.is_dir():
        raise LogUnknown("HEADROOM log folder missing (ops SSD not mounted?)")
    if not path.exists():
        return {"status": "absent", "events": [], "malformed": 0}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise LogUnknown(f"HEADROOM log unreadable: {type(exc).__name__}") from None
    events, bad = [], 0
    for line in filter(str.strip, lines):
        try:
            r = json.loads(line)
        except ValueError:
            r = None
        if _valid(r):
            events.append(r)
        else:
            bad += 1
    return {"status": "ok", "events": events, "malformed": bad}


def hold_until(r: dict) -> float:
    """When the hold from one record ends (epoch). A printed reset wins if it is sane."""
    ts, reset = _when(r["ts"]), _when(r.get("reset_at"))
    if r["event"] in RESET_TRUSTED and reset is not None and ts <= reset <= ts + MAX_RESET_S:
        return reset
    return ts + FALLBACK_HOLD_S[r["event"]]


def _state(machine: str, provider: str, events: list, now: float) -> dict:
    mine = [r for r in events if r["machine"] == machine and r["provider"] == provider]
    held = max(mine, key=hold_until, default=None)
    last = max((_when(r["ts"]) for r in mine), default=None)
    out = {"recent": last is not None and now - last < RECENT_S, "last": last}
    if held is not None and hold_until(held) > now:
        out.update(held_by=held["event"], until=hold_until(held))
    return out


def evenness(hours: Optional[dict], tolerance: float = TOLERANCE) -> dict:
    """Are the given Max seats' job-hours within +-tolerance of their mean? Pure."""
    if not hours:
        return {"status": "UNKNOWN", "reason": "no job-hours for the Max seats"}
    mean = sum(hours.values()) / len(hours)
    spread = {m: round((h - mean) / mean, 3) if mean else 0.0 for m, h in hours.items()}
    even = all(abs(s) <= tolerance for s in spread.values())
    return {"status": "even" if even else "uneven", "tolerance": tolerance,
            "mean": round(mean, 3), "spread": spread}


def _pins(amap: dict, machine: str, provider: str) -> list:
    return [a for a in amap["accounts"] if a["provider"] == provider and machine in a["machines"]]


def _sort_key(row: dict, now: float):
    age = now - row["last"] if row["last"] is not None else float("inf")
    return (not row["max"], row["state"] != "green", row["job_hours"], -age, row["machine"])


def _rank(amap, events, provider, now, candidates, hours) -> tuple[list, list]:
    ranked, skipped = [], []
    for m in candidates:
        pins = _pins(amap, m, provider)
        if len(pins) != 1:
            why = f"no {provider} pin" if not pins else f"{len(pins)} {provider} pins"
            skipped.append({"machine": m, "reason": why})
            continue
        st = _state(m, provider, events, now)
        if "held_by" in st:
            skipped.append({"machine": m, "reason": f"cooling: {st['held_by']}", "until": _iso(st["until"])})
            continue
        ranked.append({"machine": m, "max": pins[0]["max"], "last": st["last"],
                       "state": "recovered" if st["recent"] else "green",
                       "job_hours": float((hours or {}).get(m, 0.0))})
    ranked.sort(key=lambda row: _sort_key(row, now))
    return ranked, skipped


def pick(amap: dict, events: list, *, provider: str, now: float,
         candidates: Optional[list] = None, job_hours: Optional[dict] = None) -> dict:
    """The machine for the next `provider` job, why the others were skipped, and evenness."""
    candidates = list(candidates or amap["machines"])
    unknown = [m for m in candidates if m not in amap["machines"]]
    if unknown:
        raise InputError(f"{len(unknown)} candidate machine(s) not in the account map")
    ranked, skipped = _rank(amap, events, provider, now, candidates, job_hours)
    seats = [m for m in candidates if any(a["max"] for a in _pins(amap, m, provider))]
    known = job_hours is not None and all(m in job_hours for m in seats)
    even = evenness({m: float(job_hours[m]) for m in seats} if known else None)
    return {"provider": provider, "now": _iso(now), "pick": ranked[0]["machine"] if ranked else None,
            "ranked": [{k: r[k] for k in ("machine", "max", "state", "job_hours")} for r in ranked],
            "skipped": skipped, "evenness": even}


def _load_hours(path) -> Optional[dict]:
    if path is None:
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(f"job-hours table unreadable: {type(exc).__name__}") from None
    ok = isinstance(doc, dict) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                       and math.isfinite(v) and v >= 0 for v in doc.values())
    if not ok:
        raise InputError("job-hours table must map machine id to a non-negative number")
    return doc


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--provider", default="claude", choices=("claude", "codex", "cursor"))
    p.add_argument("--machines", help="comma-separated candidates (default: every mapped machine)")
    p.add_argument("--map", default=str(DEFAULT_MAP))
    p.add_argument("--log", default=os.environ.get("HEADROOM_LOG") or DEFAULT_LOG)
    p.add_argument("--job-hours", help="JSON object: machine id -> Claude job-hours this week")
    p.add_argument("--now", help="ISO time to decide at (default: now)")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    a = _args(argv)
    now = _when(a.now) if a.now else datetime.now(timezone.utc).timestamp()
    try:
        if now is None:
            raise InputError("--now is not an ISO time")
        amap, hours = load_map(a.map), _load_hours(a.job_hours)
        log = read_log(a.log)
        cands = [m.strip() for m in a.machines.split(",")] if a.machines else None
        out = pick(amap, log["events"], provider=a.provider, now=now, candidates=cands, job_hours=hours)
    except InputError as exc:
        print(f"account-picker: {exc}", file=sys.stderr)
        return 2
    except LogUnknown as exc:
        print(f"account-picker: UNKNOWN, no pick: {exc}", file=sys.stderr)
        return 3
    out["log"] = {"status": log["status"], "events": len(log["events"]), "malformed": log["malformed"]}
    print(json.dumps(out, indent=2))
    return 0 if out["pick"] else 1


if __name__ == "__main__":
    sys.exit(main())
