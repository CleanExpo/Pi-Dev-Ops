"""swarm/wiki_sync.py — Incremental Brain-1 wiki → Supabase sync.

Wraps the standalone ``scripts/sync_wiki_to_supabase.py`` logic for the
orchestrator daily cycle. Upserts changed ``*.md`` pages into the
``wiki_pages`` table when Supabase credentials are present.

Public API:
    should_run(state) -> bool
    run_sync(state, *, repo_root=None) -> WikiSyncResult
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

log = logging.getLogger("swarm.wiki_sync")

STATE_KEY = "last_wiki_sync"
MARKER_REL = ".harness/wiki_sync/.last_mtime"
SKIP_NAMES = frozenset({"log.md", "index.md", "MEMORY.md"})
_DEFAULT_SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co"
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_TAG_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class WikiSyncResult:
    synced: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    error: str | None = None


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415

    return Path(config.BRAIN1_WIKI_DIR)


def _repo_root(repo_root: Path | None) -> Path:
    return repo_root or Path(__file__).resolve().parents[1]


def _supabase_creds() -> tuple[str, str]:
    url = (
        os.environ.get("SUPABASE_UNITE_GROUP_URL")
        or os.environ.get("SUPABASE_PI_CEO_URL")
        or _DEFAULT_SUPABASE_URL
    ).rstrip("/")
    key = (
        os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY")
        or os.environ.get("SUPABASE_PI_CEO_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )
    return url, key


def _marker_path(repo_root: Path) -> Path:
    return repo_root / MARKER_REL


def _load_marker_mtime(repo_root: Path) -> float | None:
    p = _marker_path(repo_root)
    if not p.exists():
        return None
    try:
        return float(p.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _save_marker_mtime(repo_root: Path, mtime: float) -> None:
    p = _marker_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(mtime), encoding="utf-8")


def _log_mtime(wdir: Path) -> float:
    log_md = wdir / "log.md"
    if log_md.exists():
        return log_md.stat().st_mtime
    return 0.0


def should_run(state: dict) -> bool:
    """True if sync has not run today or wiki log.md changed since last sync."""
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        if date.fromisoformat(str(last)[:10]) < date.today():
            return True
    except (ValueError, TypeError):
        return True

    wdir = _wiki_dir()
    if not wdir.exists():
        return False

    repo_root = _repo_root(None)
    marker = _load_marker_mtime(repo_root)
    current = _log_mtime(wdir)
    return marker is None or current > marker


def _page_title(content: str, path: Path) -> str:
    match = _TITLE_RE.search(content)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ").title()


def _upsert_page(base_url: str, key: str, page_id: str, title: str, content: str, tags: list[str]) -> None:
    payload = json.dumps({
        "id": page_id,
        "title": title,
        "content": content[:50_000],
        "tags": tags,
        "word_count": len(content.split()),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/rest/v1/wiki_pages",
        data=payload,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"Supabase upsert HTTP {resp.status}")


def run_sync(state: dict | None = None, *, repo_root: Path | None = None) -> WikiSyncResult:
    """Sync changed wiki markdown pages to Supabase wiki_pages."""
    result = WikiSyncResult()
    root = _repo_root(repo_root)
    wdir = _wiki_dir()

    if not wdir.exists():
        result.error = f"wiki dir not found: {wdir}"
        log.debug("wiki_sync: %s", result.error)
        return result

    base_url, key = _supabase_creds()
    if not key:
        result.error = "no Supabase service key in env"
        log.debug("wiki_sync: %s", result.error)
        return result

    since = _load_marker_mtime(root)
    latest_mtime = _log_mtime(wdir)

    for md_file in sorted(wdir.rglob("*.md")):
        if md_file.name in SKIP_NAMES:
            result.skipped += 1
            continue
        try:
            mtime = md_file.stat().st_mtime
            if since is not None and mtime <= since:
                result.skipped += 1
                continue
            content = md_file.read_text(encoding="utf-8")
        except OSError as exc:
            result.skipped += 1
            result.errors.append(f"{md_file.name}: {exc}")
            continue

        page_id = str(md_file.relative_to(wdir).with_suffix(""))
        title = _page_title(content, md_file)
        tags = list(dict.fromkeys(_TAG_RE.findall(content)))[:10]

        try:
            _upsert_page(base_url, key, page_id, title, content, tags)
            result.synced += 1
            latest_mtime = max(latest_mtime, mtime)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, TimeoutError) as exc:
            msg = f"{page_id}: {exc}"
            result.errors.append(msg)
            log.warning("wiki_sync: %s", msg)

    if result.synced:
        _save_marker_mtime(root, latest_mtime)

    if state is not None:
        state[STATE_KEY] = date.today().isoformat()

    return result


__all__ = ["WikiSyncResult", "STATE_KEY", "should_run", "run_sync"]
