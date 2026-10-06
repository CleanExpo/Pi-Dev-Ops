"""Claude quota exhaustion: spot it, and read when it resets (RA-7930).

On 06/10 the Mac mini's Claude Code account hit its weekly limit. `claude -p`
printed `You've hit your weekly limit · resets Oct 9 at 1am (Australia/Brisbane)`
and exited 1, and the runner kept claiming tickets it could not build: each one
failed, counted toward quarantine, and was the account's fault, not the ticket's.

`quota_reset` reads that message. A run or a preflight whose agent exited
non-zero with it puts the node in NodeHealth's `quota` hold until the reset;
a claim it cost is released for another node, not counted as a failure. When
the reset cannot be read, the node holds for DEFAULT_HOLD_S and checks again.

The hold reason is built here from a parsed time, never copied from agent output.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Optional

DEFAULT_HOLD_S = float(os.environ.get("MESH_QUOTA_DEFAULT_HOLD_S", "3600"))
MAX_HOLD_S = 8 * 24 * 3600   # a weekly limit resets within a week; anything later is a misread
PREFIX = "Claude quota exhausted until "
TAIL_BYTES = 8192

_LIMIT = re.compile(r"hit your (?:[\w-]+ )*limit|usage limit|limit reached", re.I)
_EPOCH = re.compile(r"limit reached\|(\d{10})")   # older CLIs: `Claude AI usage limit reached|<epoch>`
_RESET = re.compile(
    r"resets?\s+(?:at\s+)?"
    r"(?:(?P<mon>[a-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?:at\s+)?)?"
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)?"
    r"(?:\s*\((?P<tz>[\w/+-]+)\))?", re.I)
_MONTHS = {m: n for n, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def quota_reset(text: str, now: float) -> Optional[float]:
    """When the quota in `text` resets (epoch seconds), or None if `text` is no quota message.

    A quota message whose reset cannot be read holds for DEFAULT_HOLD_S. Pure."""
    if not text or not _LIMIT.search(text):
        return None
    epoch = _EPOCH.search(text)
    when = float(epoch.group(1)) if epoch else _parse_reset(text, now)
    if when is None or when > now + MAX_HOLD_S:
        return now + DEFAULT_HOLD_S
    return when


def _zone(name: Optional[str]) -> Optional[tzinfo]:
    """The named IANA zone, else this machine's (None: fromtimestamp's local time)."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — Windows without tzdata raises below
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — an unknown zone is the local one, never a crash
        return None


def _hour(m: re.Match) -> Optional[tuple[int, int]]:
    hour, minute, ap = int(m["h"]), int(m["m"] or 0), (m["ap"] or "").lower()[:1]
    if ap:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ap == "p" else 0)
    return (hour, minute) if hour <= 23 and minute <= 59 else None


def _parse_reset(text: str, now: float) -> Optional[float]:
    """`resets [<Mon> <day> [at]] <h>[:mm][am|pm] [(<zone>)]` -> epoch seconds, or None.

    No date: the next such time. A time that passed within the hour, or a date
    within the last day, is a reset that is late, not one a day or a year away."""
    m = _RESET.search(text)
    hm = _hour(m) if m else None
    if hm is None:
        return None
    base = datetime.fromtimestamp(now, _zone(m["tz"]))
    try:
        if m["mon"]:
            month = _MONTHS.get(m["mon"][:3].lower())
            if month is None:
                return None
            at = base.replace(month=month, day=int(m["day"]), hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if at.timestamp() < now - 86400:
                at = at.replace(year=at.year + 1)
        else:
            at = base.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if at.timestamp() <= now - 3600:
                at += timedelta(days=1)
    except ValueError:  # Feb 30, or Feb 29 rolled into a common year
        return None
    return at.timestamp() if at.timestamp() > now else None


def problem(until: float) -> str:
    """The hold reason: names the reset in this machine's local time."""
    return PREFIX + datetime.fromtimestamp(until).astimezone().isoformat(timespec="minutes")


def held_until(reason: str) -> Optional[float]:
    """The reset a `problem()` reason names, or None for any other reason."""
    if not reason.startswith(PREFIX):
        return None
    try:
        return datetime.fromisoformat(reason[len(PREFIX):]).timestamp()
    except ValueError:
        return None


def _tail(path: Optional[Path]) -> str:
    """The end of a run log, where the CLI's last words are; "" when unreadable."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, f.seek(0, 2) - TAIL_BYTES))
            return f.read().decode(errors="replace")
    except (OSError, TypeError):
        return ""


def release_if_quota(held: list, plan: dict, now: float) -> None:
    """A build whose agent failed on quota is released for another node, not failed.

    `held` is run_agent's holder: its RunRecord's log is the agent's transcript.
    `quota_until` on the plan tells NodeHealth to hold this node until the reset."""
    rec = held[0] if held else None
    if plan.get("state") != "failed" or not getattr(getattr(rec, "proc", None), "returncode", 0):
        return
    until = quota_reset(_tail(getattr(rec, "path", None)), now)
    if until is not None:
        plan.pop("error", None)
        plan.update(state="released", quota_until=until, error_code="agent_quota")
