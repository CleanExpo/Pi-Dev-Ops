#!/usr/bin/env python3
"""youtube_transcript_fetch.py — the one network-facing part of the producer.

Split out of `youtube_transcripts.py` so that file stays under the 300-line
convention, and because what lives here is a single decision worth reading on
its own: WHICH failures mean "this video has no captions" — a permanent answer
the producer records and never re-asks — and which mean "the fetch failed", which
must be retried on the next run.

Getting that boundary wrong is not cosmetic. `youtube_transcripts._produce_one`
writes a done-marker for the permanent answer and `run` then skips that video
forever. An earlier version of this code returned None for *every* exception,
ImportError included, so one missing dependency would have retired the entire
accepted watch history as `no_captions` on the first run — silently, permanently,
and with an exit code of 0.

Re-derive the hierarchy this file leans on rather than trusting the prose:

    .venv/bin/python -c "import youtube_transcript_api as y; \
      print(y.IpBlocked.__mro__[:3]); print(y.TranscriptsDisabled.__mro__[:3])"
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("pi-ceo.youtube-transcripts")

LANGS = [s.strip() for s in os.environ.get("YT_TRANSCRIPT_LANGS", "en").split(",") if s.strip()]


def fetch_transcript(video_id: str) -> Optional[str]:
    """Captions for a video, or None ONLY when it confirmedly has none.

    Every operational failure raises instead — a missing install, a blocked IP,
    an unparsable reply — so the caller counts it as failed and tries again on a
    later run.

    `CouldNotRetrieveTranscript` is deliberately NOT the test for absence: it is
    equally the base class of `IpBlocked`, `RequestBlocked`, `YouTubeRequestFailed`
    and `PoTokenRequired`, which are precisely the throttling symptoms a retry
    exists for. Only `TranscriptsDisabled` (the uploader turned captions off) and
    `NoTranscriptFound` (nothing in `LANGS`) are statements about the video.

    The import sits inside the call so neither this module nor the test suite
    needs the dependency at collection time.
    """
    try:
        from youtube_transcript_api import (  # noqa: PLC0415
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )
    except ImportError as exc:  # operational — never "this video has no captions"
        raise ImportError(
            "youtube-transcript-api not installed — `uv pip install youtube-transcript-api`"
        ) from exc

    try:
        rows = YouTubeTranscriptApi().fetch(video_id, languages=LANGS)
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        log.info("no captions for %s: %s", video_id, type(exc).__name__)
        return None
    text = " ".join(str(getattr(r, "text", "") or "") for r in rows).strip()
    return text or None
