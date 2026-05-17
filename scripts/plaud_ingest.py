"""Plaud → Brain ingester. Spec: docs/superpowers/specs/2026-05-17-plaud-brain-ingestion-design.md"""
import re
import unicodedata


def slug_from_name(name: str, fallback_id: str = "") -> str:
    """ASCII-fold, lowercase, replace non-alphanum with '-', collapse repeats."""
    if not name or not name.strip():
        return fallback_id
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or fallback_id


def split_segments(segments: list[dict], max_chars: int = 50_000) -> list[list[dict]]:
    """Split a list of transcript segments into chunks whose total char count
    stays below max_chars. Never split a single segment. A pathological segment
    larger than max_chars is emitted as its own (oversized) part."""
    parts: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for seg in segments:
        seg_chars = len(seg["text"])
        if current and current_chars + seg_chars > max_chars:
            parts.append(current)
            current = []
            current_chars = 0
        current.append(seg)
        current_chars += seg_chars
    if current:
        parts.append(current)
    return parts


def format_duration_human(ms: int) -> str:
    total_s = ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def format_timestamp(ms: int) -> str:
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def format_page(
    *,
    plaud_id: str,
    title: str,
    recorded_at: str,
    duration_ms: int,
    ingested_at: str,
    audio_url: str,
    summary_md: str | None,
    segments: list[dict],
    part: tuple[int, int] | None = None,
) -> str:
    """Render one wiki page (markdown with YAML frontmatter)."""
    fm_lines = [
        "---",
        "type: plaud-recording",
        f"plaud_id: {plaud_id}",
        f"recorded_at: {recorded_at}",
        f"duration_ms: {duration_ms}",
        f"duration_human: {format_duration_human(duration_ms)}",
        "source: plaud-notepin-s",
        f"ingested_at: {ingested_at}",
        "tags: []",
    ]
    if part is not None:
        fm_lines.append(f"part: {part[0]}/{part[1]}")
    fm_lines.append("---")

    body: list[str] = ["", f"# {title}", "", f"**Audio:** {audio_url}",
                       f"**Duration:** {format_duration_human(duration_ms)}", ""]
    if summary_md and (part is None or part[0] == 1):
        body.append(summary_md)
        body.append("")
    body.append("## Transcript")
    for seg in segments:
        start = format_timestamp(seg["start_ms"])
        end = format_timestamp(seg["end_ms"])
        speaker = seg.get("speaker", "?")
        body.append(f"[{start} - {end}] {speaker}: {seg['text']}")

    return "\n".join(fm_lines + body) + "\n"


import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("plaud_ingest")


def _iso_24h_ago() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()


def load_state(path: Path) -> dict:
    """Read state file. Missing or corrupt → fresh default (24h-ago)."""
    default = {
        "last_seen_id": "",
        "last_seen_ts": _iso_24h_ago(),
        "last_run_status": "fresh",
        "last_error": None,
        "consecutive_failures": 0,
    }
    if not path.exists():
        return default
    try:
        return {**default, **json.loads(path.read_text())}
    except (json.JSONDecodeError, OSError) as e:
        log.warning("plaud-state.json corrupt (%s); using fresh default", e)
        return default


def save_state(path: Path, state: dict) -> None:
    """Atomic write via tmp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)
