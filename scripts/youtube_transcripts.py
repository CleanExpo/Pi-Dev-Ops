#!/usr/bin/env python3
"""youtube_transcripts.py — turn watched videos into wiki source clips.

THE MISSING PRODUCER
--------------------
`swarm/wiki_ingest.py` has parsed YouTube clips since it was written:
`_enrich_youtube_frontmatter` reads a `source:` URL, pulls the channel out of
`author:`, and threads it into the ingest prompt. Nothing ever wrote that file.
The consumer has been waiting for a producer that did not exist, so no video the
owner watched ever reached the wiki.

This is that producer, and it is deliberately the only new part of the chain.
Everything downstream already runs on its own:

    this script -> Sources/*.md
                -> swarm/sources_watcher.run_cycle()     (orchestrator cycle)
                -> swarm/wiki_ingest.ingest_file()       (guarded by ingest_guard)
                -> swarm/gap_detector / enhancement_scout -> Linear / Board

Re-derive that the chain is wired, rather than trusting this comment:

    grep -nE "sources_watcher|gap_detector|enhancement_scout" swarm/orchestrator.py

INPUT
-----
The catalog `app.server.youtube_intent` already maintains, filled by either of
the two lanes the owner chose: the OAuth `pull-live` route or a Google Takeout
drop through `import-takeout`. Only items this catalog already classified
`accepted` are fetched — the strategic-relevance decision is made there, not
here, so this script never widens what gets ingested.

SAFETY
------
Captions are attacker-controlled text. This script does not interpret them: it
writes them to a file. Interpretation happens in `wiki_ingest`, behind
`swarm/ingest_guard.fence_source` and its target allowlist. Nothing here is a
trust boundary, and nothing here should ever grow one.

USAGE
    python3 scripts/youtube_transcripts.py --dry-run     # plan only, no writes
    python3 scripts/youtube_transcripts.py --limit 5
    YOUTUBE_TRANSCRIPTS_ENABLED=1 python3 scripts/youtube_transcripts.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

log = logging.getLogger("pi-ceo.youtube-transcripts")

# Per-run cap. YouTube throttles by IP, and a first run against a full watch
# history would fetch hundreds of transcripts in a burst and get the host
# blocked — which looks exactly like "the feature does not work".
DEFAULT_LIMIT = int(os.environ.get("YT_TRANSCRIPT_LIMIT", "25"))
LANGS = [s.strip() for s in os.environ.get("YT_TRANSCRIPT_LANGS", "en").split(",") if s.strip()]
MARKER_PATH = REPO_ROOT / ".harness" / "youtube_transcripts_done.jsonl"

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
_SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Result:
    """What one run did. Every list is a path a reader may need to act on."""

    written: list[str] = field(default_factory=list)
    no_captions: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped_done: int = 0
    considered: int = 0


def enabled() -> bool:
    """Whether the producer may write. Default OFF, like every other new lane."""
    return os.environ.get("YOUTUBE_TRANSCRIPTS_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def video_id_of(item: dict[str, Any]) -> Optional[str]:
    """The 11-character YouTube id for a catalog row, or None.

    Takeout rows carry a `titleUrl`-derived `url` and often a `video_id` that is
    really that same URL, so a bare `video_id` is only trusted when it already
    looks like an id.
    """
    raw = str(item.get("video_id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    for candidate in (raw, str(item.get("url") or ""), str(item.get("video_key") or "")):
        m = _VIDEO_ID_RE.search(candidate)
        if m:
            return m.group(1)
    return None


def _load_done() -> set[str]:
    """Video ids already turned into a clip. Absent marker file means none."""
    if not MARKER_PATH.exists():
        return set()
    done: set[str] = set()
    for line in MARKER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            done.add(json.loads(line)["video_id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # a torn line must not lose the whole marker
    return done


def _mark_done(video_id: str, outcome: str) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MARKER_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"video_id": video_id, "outcome": outcome}) + "\n")


def accepted_videos(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Catalog rows already classified `accepted`, newest-looking first.

    Relevance is the catalog's decision (`youtube_intent.classify_item`), not
    this script's. Re-deciding it here would give the estate two disagreeing
    definitions of "strategic".
    """
    return [v for v in state.get("videos", []) if v.get("status") == "accepted"]


def clip_markdown(item: dict[str, Any], video_id: str, transcript: str) -> str:
    """Render the Sources clip in the shape wiki_ingest already parses.

    `source:` MUST hold a youtube.com/youtu.be URL: that string is the only gate
    on `_enrich_youtube_frontmatter` doing anything at all, and dropping it
    silently turns the clip into an ordinary note. Verified by breaking it — the
    round-trip test fails.

    `author:` supplies the channel. The consumer's `_extract_channel` accepts
    both `"[[Name]]"` and a bare `"Name"` (its brackets are optional), so the
    wikilink form here is for the vault's own conventions — Obsidian resolves it
    to a channel page — not because the parser requires it.

    `channel:` is deliberately NOT written here. Letting the consumer inject it
    is what exercises the code path this producer exists to feed.
    """
    channel = str(item.get("channel") or "unknown").replace("[", "").replace("]", "").strip()
    title = str(item.get("title") or video_id).replace("\n", " ").strip()
    url = str(item.get("url") or f"https://www.youtube.com/watch?v={video_id}")
    watched = str(item.get("watched_at") or item.get("ingested_at") or "")
    return (
        "---\n"
        f'title: "{title}"\n'
        f"source: {url}\n"
        f'author: "[[{channel}]]"\n'
        "type: clip\n"
        f"video_id: {video_id}\n"
        + (f"watched: {watched}\n" if watched else "")
        + "---\n\n"
        f"# {title}\n\n"
        f"{transcript.strip()}\n"
    )


def clip_filename(item: dict[str, Any], video_id: str) -> str:
    """`YYYYMMDD-<videoid>.md` when a date is known, else `<videoid>.md`.

    The id, never the title, carries identity: titles contain slashes and quotes,
    and two videos can share one. Any date is sanitised rather than trusted —
    it comes from Takeout JSON.
    """
    stamp = str(item.get("watched_at") or item.get("ingested_at") or "")[:10].replace("-", "")
    prefix = f"{stamp}-" if stamp.isdigit() and len(stamp) == 8 else ""
    return _SAFE_SLUG_RE.sub("", f"{prefix}{video_id}") + ".md"


def _default_fetcher(video_id: str) -> Optional[str]:
    """Fetch captions with youtube-transcript-api, or None when there are none.

    Imported inside the call so the module — and its tests — do not require the
    dependency, and so a missing install reports itself once rather than
    breaking collection.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415
    except ImportError:
        log.error("youtube-transcript-api not installed — `uv pip install youtube-transcript-api`")
        return None
    try:
        rows = YouTubeTranscriptApi().fetch(video_id, languages=LANGS)
    except Exception as exc:  # noqa: BLE001 — the library raises many distinct types
        log.info("no transcript for %s: %s", video_id, type(exc).__name__)
        return None
    text = " ".join(str(getattr(r, "text", "") or "") for r in rows).strip()
    return text or None


def run(
    sources_dir: Path,
    *,
    state: Optional[dict[str, Any]] = None,
    fetcher: Optional[Callable[[str], Optional[str]]] = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
) -> Result:
    """Write one clip per accepted, un-fetched video. Returns what happened.

    `fetcher` is injectable so the whole path is testable without the network:
    the real one is the only part that cannot be exercised offline.
    """
    fetch = fetcher or _default_fetcher
    catalog = state if state is not None else _load_state()
    done = _load_done()
    result = Result()

    for item in accepted_videos(catalog):
        if len(result.written) >= limit:
            log.info("stopping at limit=%d — rerun to continue", limit)
            break
        video_id = video_id_of(item)
        if not video_id:
            result.failed.append(str(item.get("video_key") or item.get("title") or "?"))
            continue
        result.considered += 1
        if video_id in done:
            result.skipped_done += 1
            continue
        _produce_one(item, video_id, sources_dir, fetch, result, dry_run)

    return result


def _produce_one(
    item: dict[str, Any],
    video_id: str,
    sources_dir: Path,
    fetch: Callable[[str], Optional[str]],
    result: Result,
    dry_run: bool,
) -> None:
    """Fetch one video and write its clip, recording the outcome either way."""
    transcript = fetch(video_id)
    if not transcript:
        result.no_captions.append(video_id)
        if not dry_run:
            # Recorded so an uncaptioned video is not re-fetched on every run —
            # "no captions" is a permanent answer, and re-asking invites throttling.
            _mark_done(video_id, "no_captions")
        return

    target = sources_dir / clip_filename(item, video_id)
    result.written.append(str(target))
    if dry_run:
        return
    sources_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(clip_markdown(item, video_id, transcript), encoding="utf-8")
    _mark_done(video_id, "written")


def _load_state() -> dict[str, Any]:
    from app.server import youtube_intent  # noqa: PLC0415
    return youtube_intent.load_state()


def _sources_dir() -> Path:
    from swarm import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR).parent / "Sources"


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="YouTube transcripts -> wiki Sources clips")
    ap.add_argument("--dry-run", action="store_true", help="plan only; no files, no markers")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args()

    if not args.dry_run and not enabled():
        log.info("YOUTUBE_TRANSCRIPTS_ENABLED not set — nothing written (use --dry-run to plan)")
        return 0

    result = run(_sources_dir(), limit=args.limit, dry_run=args.dry_run)
    print(json.dumps({
        "written": len(result.written),
        "no_captions": len(result.no_captions),
        "failed": len(result.failed),
        "skipped_already_done": result.skipped_done,
        "considered": result.considered,
        "dry_run": args.dry_run,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
