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
