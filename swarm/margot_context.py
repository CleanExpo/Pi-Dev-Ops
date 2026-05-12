"""swarm/margot_context.py — RA-3023 (Plan agent-empowerment 2026-05-13 T2):
hot-pin loader for the $2B pathway page.

Every Margot turn must reference the pathway page (the operating constraints
filter for the entire empire). Without hot-pinning, Gemma 4 / Llama-class
local models hallucinate filenames and substitute generic VC-speak. This
module forces the actual file content into Margot's prompt every turn.

Read order:
  1. Filesystem (the canonical wiki path on Phill's Mac mini)
  2. Supabase wiki_pages (fallback if filesystem path moves OR Margot is
     running in a cloud worker without filesystem access)

Returns None only if both paths fail — Margot then proceeds without the
hot-pin (degraded behaviour, not crash).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("swarm.margot_context")

_PATHWAY_FILE = Path(
    "/Users/phill-mac/2nd Brain/2nd Brain/Wiki/pathway-to-2b-2026-2028.md"
)
_PATHWAY_SLUG = "pathway-to-2b-2026-2028"


def _load_from_filesystem() -> str | None:
    try:
        return _PATHWAY_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError) as exc:
        log.debug("margot_context: filesystem load failed (%s)", exc)
        return None


def _load_from_supabase() -> str | None:
    """Fallback: pull from wiki_pages on Unite-Group Supabase by slug."""
    url = os.environ.get("SUPABASE_UNITE_GROUP_URL")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY")
    if not (url and key):
        log.debug("margot_context: Supabase creds unset — skipping fallback")
        return None
    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.debug("margot_context: httpx unavailable (%s) — skipping fallback", exc)
        return None
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{url}/rest/v1/wiki_pages",
                params={"slug": f"eq.{_PATHWAY_SLUG}", "select": "content", "limit": 1},
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
            )
            r.raise_for_status()
            rows = r.json()
            if rows and isinstance(rows, list) and rows[0].get("content"):
                return rows[0]["content"]
    except Exception as exc:  # noqa: BLE001
        log.debug("margot_context: Supabase fallback failed (%s)", exc)
    return None


def load_pathway() -> str | None:
    """Return the pathway page content, or None if neither source resolves."""
    content = _load_from_filesystem()
    if content:
        return content
    return _load_from_supabase()


__all__ = ["load_pathway"]
