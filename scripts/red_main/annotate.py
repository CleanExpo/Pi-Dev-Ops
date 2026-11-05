"""Owner and age on every AMBER/RED watcher line, and escalation of unowned ones (RA-8174).

The MacBook fleet watcher pipes its facts through `red_main_watch.py annotate`. Each
AMBER or RED line is keyed by its text with the numbers blanked (so "idle 40 min" and
"idle 55 min" are the same problem), first-seen time is remembered, and the line gets
"[owner: X; age: Nm]". Owner comes from the board card that carries the line's
watch_key. A line unowned for 30+ minutes becomes an open W-WATCH-<key> board card;
when the line is absent from a COMPLETE read (input ends with "# END FACTS") the card
closes. Live red-main cards are printed first.
"""
from __future__ import annotations

import datetime
import hashlib
import re

from red_main.common import WATCH_PREFIX, env_minutes, minutes_since, stamp
from red_main.board import live_red_cards

FLAGGED = re.compile(r"^(RED|AMBER)\b")
END_MARKER = "# END FACTS"
TAG = re.compile(r"\s*\[owner: [^\]]*\]\s*$")
OWNERLESS = {None, "", "Guardian watcher", "fleet watcher"}


def key(line: str) -> str:
    norm = re.sub(r"\s+", " ", re.sub(r"\d+", "#", line.strip()))
    return hashlib.sha1(norm.encode()).hexdigest()[:10]


def owner_of(card: dict | None) -> str | None:
    if not card or card.get("status") == "done":
        return None
    who = card.get("claimed_by") or card.get("owner")
    return None if who in OWNERLESS else str(who)


def tag(line: str, owner: str | None, age: int | None) -> str:
    return f"{line.rstrip()} [owner: {owner or 'NONE'}; age: {'?' if age is None else age}m]"


def _red_main_rows(d: dict) -> list[tuple[str, dict]]:
    """(untagged line, card) for every live red-main card."""
    rows = []
    for c in live_red_cards(d):
        names = ", ".join(str(r.get("name")) for r in (c.get("failing") or [])[:3])
        extra = f"; {c['pr_overdue']}" if c.get("pr_overdue") else ""
        rows.append((f"RED {c.get('repo')} {c.get('branch')} red since {c.get('red_since')} ({names}){extra}", c))
    return rows


def red_main_lines(d: dict, at: datetime.datetime) -> list[str]:
    return [tag(line, owner_of(c), minutes_since(c.get("red_since"), at)) for line, c in _red_main_rows(d)]


def _escalate(d: dict, k: str, line: str, at: datetime.datetime, old: dict | None) -> dict:
    """Open (or reopen, for a line that came back) the line's W-WATCH card."""
    card = {
        "id": WATCH_PREFIX + k, "watch_key": k, "status": "open", "priority": "P1", "owner": None,
        "claimed_by": None, "created": stamp(at), "updated": stamp(at),
        "title": f"UNOWNED 30+ min watcher line: {line.strip()[:200]}",
        "blocker": "Fleet watcher line with no owner for 30+ minutes. Claim it (linear + claimed_by) or fix it."}
    if old is not None:
        old.update({**card, "created": old.get("created", stamp(at))})
        return old
    d.setdefault("jobs", []).append(card)
    return card


def annotate(lines: list[str], d: dict, seen: dict, at: datetime.datetime) -> tuple[list[str], dict, bool]:
    """(output lines, new first-seen map, board changed)."""
    cards = {j.get("watch_key"): j for j in d.get("jobs", []) if isinstance(j, dict) and j.get("watch_key")}
    out, now_seen, changed = red_main_lines(d, at), {}, False
    own = {line for line, _ in _red_main_rows(d)}
    for raw in lines:
        # Review r3: an already-annotated line (a retry feeding output back in) is the same
        # problem: strip its tag and key it again, or its live card would read as cleared.
        line = TAG.sub("", raw.rstrip("\n"))
        if line in own:
            continue   # this watcher's own red-main line echoed back; printed above already
        if not FLAGGED.match(line):
            out.append(raw.rstrip("\n"))
            continue
        k = key(line)
        now_seen[k] = seen.get(k) or stamp(at)
        age = minutes_since(now_seen[k], at)
        card = cards.get(k)
        unowned = card is None or card.get("status") == "done"
        if unowned and age is not None and age >= env_minutes("RED_MAIN_ESCALATE_MIN", 30).total_seconds() // 60:
            card = _escalate(d, k, line, at, card)
            changed = True
        owner = owner_of(card)
        if owner is None and card is not None and card.get("status") != "done":
            owner = f"NONE, escalated to board {card['id']}"
        out.append(tag(line, owner, age))
    # Review r1: only a complete facts read may close a card whose line is absent. The
    # caller ends its facts with END_MARKER; a truncated or partial stream lacks it.
    complete = any(x.strip() == END_MARKER for x in lines)
    closed = _close_gone(d, now_seen, at) if complete else False
    if not complete:
        now_seen = {**seen, **now_seen}   # keep first-seen times for lines this read did not cover
    return out, now_seen, closed or changed


def _close_gone(d: dict, seen: dict, at: datetime.datetime) -> bool:
    changed = False
    for j in d.get("jobs", []):
        if (isinstance(j, dict) and str(j.get("id", "")).startswith(WATCH_PREFIX) and j.get("status") != "done"
                and j.get("watch_key") not in seen):
            j.update({"status": "done", "updated": stamp(at), "result": f"Watcher line cleared {stamp(at)}."})
            changed = True
    return changed
