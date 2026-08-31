#!/usr/bin/env python3
"""youtube_transcript_state.py — what has already been fetched, and where things live.

Split out of `youtube_transcripts.py` to keep that file under the 300-line
convention. The seam is deliberate rather than arbitrary: everything here is
durable state and location, and the producer beside it is the loop that reads
and writes through these four functions.

The done-marker is the part worth reading carefully. It is append-only JSONL,
one record per video, and `run` skips any id it names — so a record written here
is effectively permanent, undoable only by hand-editing the file. That is why
`mark_done` is called for exactly two outcomes, both of which are statements
about the video itself: a transcript was written, or the video confirmedly has
no captions. An operational failure (a missing dependency, a blocked IP) must
never reach it, or one bad run retires the backlog forever. See
`youtube_transcripts._produce_one` for the enforcement, and
`youtube_transcript_fetch.fetch_transcript` for how the two are told apart.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKER_PATH = REPO_ROOT / ".harness" / "youtube_transcripts_done.jsonl"


def load_done() -> set[str]:
    """Video ids already resolved. An absent marker file means none.

    A torn line is skipped rather than fatal: a half-written record costs one
    video a re-fetch, while raising here would strand the whole history.
    """
    if not MARKER_PATH.exists():
        return set()
    done: set[str] = set()
    for line in MARKER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            done.add(json.loads(line)["video_id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # a torn line must not lose the whole marker
    return done


def mark_done(video_id: str, outcome: str) -> None:
    """Append one permanent "never fetch this again" record.

    Only for outcomes that are statements about the video — `written` or
    `no_captions`. Never for an operational failure; see the module docstring.
    """
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MARKER_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"video_id": video_id, "outcome": outcome}) + "\n")


def load_state() -> dict[str, Any]:
    """The youtube-intent catalog, fed by both the OAuth and Takeout lanes.

    Imported lazily so a dry run and the tests do not pull in the server
    package just to read a JSON file.
    """
    from app.server import youtube_intent  # noqa: PLC0415
    return youtube_intent.load_state()


def sources_dir() -> Path:
    """The wiki's `Sources/` drop zone — the front door `sources_watcher` polls.

    Derived from `BRAIN1_WIKI_DIR` rather than configured separately, so clips
    land beside the vault the watcher already reads and there is one place to
    point at a different machine.
    """
    from swarm import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR).parent / "Sources"
