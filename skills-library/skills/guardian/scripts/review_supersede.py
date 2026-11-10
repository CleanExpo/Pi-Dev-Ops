#!/usr/bin/env python3
"""Close review cards that a newer review round of the same stream has replaced (stdlib only, python 3.9 ok).

Why: each exact-SHA review round adds a card (worktree rv-<stream>-<sha>) and parks it in `review`
for a consumer who never closes it. On 01/11/2026 the board held 76 `review` cards; 19 were older
rounds whose evidence a later head had already made stale. Nobody's job, so they never left.

Rule: cards are grouped by the rv-<stream>-<sha> worktree named as a word in claimed_by (never the
note). Within a stream the newest card by `created` stands; every OLDER card still in `review`
becomes `done` with superseded_by pointing at the newest. Only `created` ranks a round: `updated` is a
mutable edit time, and ranking by it closed the live round when an older card was edited (review of
6e575cff). A stream with a missing, unparseable or naive `created`, a tie for newest, or a card whose
id is not unique on the board is left alone (unknown is not stale). Cards with no rv- stream are never
touched.

Usage: review_supersede.py [--jobs PATH] [--apply]   (default is a dry run that changes nothing)
"""
import argparse, datetime as dt, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs_lock  # noqa: E402

DEFAULT_JOBS = "/Volumes/Mini Mini 2T Storage/ops/jobs.json"
STREAM = re.compile(r"\b(rv-[a-z0-9-]+?)-([0-9a-f]{7,40})\b")


def parse_ts(s):
    if not isinstance(s, str) or not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)  # +1000 -> +10:00
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else None  # naive times cannot be ordered against the rest


def _match(job):
    # claimed_by only, as a whole word: a note that MENTIONS another worktree is prose, and
    # reading it closed an unrelated card (review of eeb5bcab).
    words = str(job.get("claimed_by") or "").split()
    return next((STREAM.fullmatch(w) for w in words if STREAM.fullmatch(w)), None)


def stream_of(job):
    m = _match(job)
    return m.group(1) if m else None


def sha_of(job):
    m = _match(job)
    return m.group(2).lower() if m else None


def same_head(a, b):
    # Worktree names abbreviate SHAs to any width from 7 to 40, so 15d704f and its full
    # 40-character form are one head. Prefix-compatible means "maybe the same": not stale.
    return bool(a and b and (a.startswith(b) or b.startswith(a)))


def stamp(job):
    # `created` only. Every earlier choice that let a mutable or fallback time rank a round closed
    # the live one: invalid `updated` falling back to `created` (eeb5bcab), and an edited older
    # card outranking the live round by `updated` (6e575cff).
    return parse_ts(job.get("created"))


def _plan(jobs):
    """Return [(old_job, newest_job)] for review cards superseded within their stream."""
    seen, dup = set(), set()
    for j in jobs:
        i = j.get("id")
        (dup if i in seen else seen).add(i)
    groups = {}
    for j in jobs:
        s = stream_of(j)
        # Every card ranks, including ones already superseded: `created` never changes on
        # close, so a closed round cannot become "newest", and skipping a card marked
        # superseded but still in `review` left it open forever (review of 83b573c2).
        if s:
            groups.setdefault(s, []).append(j)
    out = []
    for cards in groups.values():
        if len(cards) < 2:
            continue
        if any(c.get("id") in dup or not c.get("id") for c in cards):
            continue  # a duplicate id cannot be told apart, so no card in it is provably stale
        stamped = [(stamp(c), c) for c in cards]
        if any(t is None for t, _ in stamped):
            continue
        stamped.sort(key=lambda p: p[0])
        if stamped[-1][0] == stamped[-2][0]:
            continue  # a tie for newest names no live round; array order is not evidence
        newest = stamped[-1][1]
        # A later card for the SAME head is a re-run, not a newer round: the earlier card may
        # hold that head's only finished result (live board, 01/11/2026: rv-dr-4ca95f36).
        out += [(c, newest) for _, c in stamped[:-1]
                if c.get("status") == "review" and not same_head(sha_of(c), sha_of(newest))]
    return out


def plan(jobs):
    return [(o["id"], n["id"]) for o, n in _plan(jobs)]


def apply(d, now=None):
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pairs = _plan(d.get("jobs", []))
    for j, newest in pairs:  # mutate the planned objects themselves, never a re-lookup by id
        new = newest["id"]
        j["status"] = "done"
        j["superseded_by"] = new
        j["updated"] = now
        # Its own field: overwriting an existing closed_note lost board content (review of 83b573c2).
        j["supersede_note"] = (f"Superseded by newer review round {new} of the same stream; this "
                               "exact-SHA evidence is stale. Closed by guardian review_supersede.")
    if pairs:
        d["updated"] = now  # the board-level stamp every other guardian writer refreshes
    return [(j["id"], n["id"]) for j, n in pairs]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default=DEFAULT_JOBS)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if not a.apply:
        with open(a.jobs) as f:
            pairs = plan(json.load(f).get("jobs", []))
    else:
        pairs = []
        jobs_lock.update_jobs(a.jobs, lambda d: bool(pairs.extend(apply(d)) or pairs))
    for old, new in pairs:
        print(f"{'closed' if a.apply else 'would close'} {old} -> superseded_by {new}")
    print(f"{len(pairs)} superseded review card(s){'' if a.apply else ' (dry run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
