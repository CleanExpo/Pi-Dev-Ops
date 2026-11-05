"""Shared constants and the GitHub CLI seam for the red-main watcher (RA-8174).

Stdlib only, Python 3.9+, no model and no paid API. Every reader returns a reason
string when it could not answer: a failed read is UNKNOWN, never green.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess

OK, FAIL, UNKNOWN = "OK", "FAIL", "UNKNOWN"
TS = "%Y-%m-%dT%H:%M%z"
CARD_PREFIX = "W-MAIN-RED-"
WATCH_PREFIX = "W-WATCH-"


def env_minutes(name: str, default: int) -> datetime.timedelta:
    return datetime.timedelta(minutes=int(os.environ.get(name, str(default))))


def org() -> str:
    return os.environ.get("RED_MAIN_ORG", "CleanExpo")


def ops_dir() -> str:
    return os.environ.get("RED_MAIN_OPS", "/Volumes/Mini Mini 2T Storage/ops")


def state_dir() -> str:
    return os.environ.get("RED_MAIN_STATE_DIR", os.path.expanduser("~/.local/state"))


def max_launches() -> int:
    return int(os.environ.get("RED_MAIN_MAX_LAUNCHES", "2"))


def gh_path() -> str:
    return os.environ.get("RED_MAIN_GH", "/opt/homebrew/bin/gh")


def gh_timeout() -> float:
    return float(os.environ.get("RED_MAIN_GH_TIMEOUT", "60"))


def now() -> datetime.datetime:
    """The clock. RED_MAIN_NOW (a TS string) pins it for tests."""
    pinned = os.environ.get("RED_MAIN_NOW")
    if pinned:
        return datetime.datetime.strptime(pinned, TS)
    return datetime.datetime.now().astimezone()


def stamp(t: datetime.datetime) -> str:
    return t.strftime(TS)


def parse_time(value) -> datetime.datetime | None:
    """A board TS string or a GitHub ISO-8601 time; None when it is neither."""
    if not isinstance(value, str) or not value:
        return None
    for fmt in (TS, "%Y-%m-%dT%H:%M:%SZ"):
        try:
            t = datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    return None


def minutes_since(value, at: datetime.datetime) -> int | None:
    t = parse_time(value)
    return None if t is None else max(0, int((at - t).total_seconds() // 60))


def gh(*args) -> tuple[bool, str, str]:
    """(ok, stdout, reason). reason = first stderr line, timeout or spawn error."""
    try:
        r = subprocess.run([gh_path(), *args], capture_output=True, text=True, timeout=gh_timeout())
    except subprocess.TimeoutExpired:
        return False, "", f"gh timed out after {gh_timeout():g}s"
    except OSError as e:
        return False, "", f"gh could not run: {type(e).__name__}: {e}"
    if r.returncode != 0:
        line = next((x.strip() for x in r.stderr.splitlines() if x.strip()), "")
        return False, "", f"gh exit {r.returncode}: {line}" if line else f"gh exit {r.returncode}"
    return True, r.stdout, ""


def gh_json(*args):
    """(parsed, reason). parsed is None when the call failed or was not JSON."""
    ok, out, why = gh(*args)
    if not ok:
        return None, why
    try:
        return json.loads(out), ""
    except ValueError:
        return None, f"gh output not JSON: {out.strip()[:80]!r}"


def short(repo: str) -> str:
    return repo.split("/")[-1]


def card_id(repo: str) -> str:
    return CARD_PREFIX + short(repo)
