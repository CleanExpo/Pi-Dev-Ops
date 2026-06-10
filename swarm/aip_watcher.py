"""swarm/aip_watcher.py — Wiki ```aip block scanner + Supabase entity flush.

Scans Brain-1 wiki pages for fenced ```aip blocks, queues unseen payloads,
then upserts entities into ``aip_entities`` when Supabase credentials exist.

Public API:
    should_run(state) -> bool
    run_daily(state, *, repo_root=None) -> AipWatcherResult
    flush_queue(*, repo_root=None) -> AipFlushResult
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.aip_watcher")

STATE_KEY = "last_aip_watcher"
QUEUE_REL = ".harness/aip_watcher/queue.jsonl"
SEEN_REL = ".harness/aip_watcher/seen.json"
_AIP_BLOCK_RE = re.compile(r"```aip\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass
class AipWatcherResult:
    entities_queued: int = 0
    pages_scanned: int = 0
    skipped: int = 0
    error: str | None = None
    queued_uris: list[str] = field(default_factory=list)


@dataclass
class AipFlushResult:
    flushed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    error: str | None = None


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _repo_root(repo_root: Path | None) -> Path:
    return repo_root or Path(__file__).resolve().parents[1]


def _load_seen(repo_root: Path) -> set[str]:
    p = repo_root / SEEN_REL
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("hashes", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_seen(repo_root: Path, seen: set[str]) -> None:
    p = repo_root / SEEN_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hashes": sorted(seen)}, indent=2), encoding="utf-8")


def _block_hash(page: str, body: str) -> str:
    return hashlib.sha256(f"{page}\n{body}".encode()).hexdigest()


def _supabase_creds() -> tuple[str, str]:
    url = (
        os.environ.get("SUPABASE_UNITE_GROUP_URL")
        or os.environ.get("SUPABASE_PI_CEO_URL")
        or ""
    ).rstrip("/")
    key = (
        os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY")
        or os.environ.get("SUPABASE_PI_CEO_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )
    return url, key


def _entity_row(row: dict) -> dict | None:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return None
    uri = row.get("uri") or _extract_uri(payload)
    kind = payload.get("kind")
    eid = payload.get("id") or payload.get("entity_id")
    if not uri or not kind or not eid:
        return None
    props = {
        k: v
        for k, v in payload.items()
        if k not in {"kind", "id", "entity_id", "uri", "entity_uri"}
    }
    page = row.get("page", "")
    source = {
        "origin": "wiki",
        "ref": f"{page}#{row.get('hash', '')[:12]}",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "uri": uri,
        "kind": str(kind),
        "id": str(eid),
        "properties": props,
        "source": source,
    }


def _upsert_entity(base_url: str, key: str, entity: dict) -> None:
    payload = json.dumps(entity).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/rest/v1/aip_entities",
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
            raise RuntimeError(f"aip_entities upsert HTTP {resp.status}")


def flush_queue(*, repo_root: Path | None = None) -> AipFlushResult:
    """Upsert queued wiki ```aip entities into Supabase aip_entities."""
    result = AipFlushResult()
    root = _repo_root(repo_root)
    queue_path = root / QUEUE_REL
    if not queue_path.exists():
        return result

    base_url, key = _supabase_creds()
    if not key or not base_url:
        result.error = "no Supabase URL/key in env"
        return result

    pending: list[str] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            result.skipped += 1
            continue

        entity = _entity_row(row)
        if not entity:
            result.skipped += 1
            pending.append(line)
            continue

        try:
            _upsert_entity(base_url, key, entity)
            result.flushed += 1
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, TimeoutError) as exc:
            result.failed += 1
            msg = f"{entity.get('uri')}: {exc}"
            result.errors.append(msg)
            pending.append(line)
            log.warning("aip_watcher flush: %s", msg)

    if result.flushed:
        queue_path.write_text(
            ("\n".join(pending) + "\n") if pending else "",
            encoding="utf-8",
        )

    return result


def _extract_uri(payload: dict) -> str | None:
    for key in ("uri", "id", "entity_uri"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("aip://"):
            return val
    kind = payload.get("kind")
    eid = payload.get("id") or payload.get("entity_id")
    if kind and eid:
        return f"aip://unite-group/{kind}/{eid}"
    return None


def should_run(state: dict) -> bool:
    """True if AIP wiki scan has not run today."""
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(str(last)[:10]) < date.today()
    except (ValueError, TypeError):
        return True


def run_daily(state: dict | None = None, *, repo_root: Path | None = None) -> AipWatcherResult:
    """Scan wiki for ```aip blocks; append new ones to the local queue."""
    result = AipWatcherResult()
    root = _repo_root(repo_root)
    wdir = _wiki_dir()

    if not wdir.exists():
        result.error = f"wiki dir not found: {wdir}"
        return result

    seen = _load_seen(root)
    queue_path = root / QUEUE_REL
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    for md_file in sorted(wdir.rglob("*.md")):
        if md_file.name in {"index.md", "log.md", "MEMORY.md"}:
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError as exc:
            log.debug("aip_watcher: skip %s (%s)", md_file.name, exc)
            result.skipped += 1
            continue

        result.pages_scanned += 1
        rel_page = str(md_file.relative_to(wdir))

        for match in _AIP_BLOCK_RE.finditer(content):
            body = match.group(1).strip()
            if not body:
                continue
            h = _block_hash(rel_page, body)
            if h in seen:
                result.skipped += 1
                continue

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                log.debug("aip_watcher: invalid JSON in %s", rel_page)
                result.skipped += 1
                continue

            if not isinstance(payload, dict):
                result.skipped += 1
                continue

            uri = _extract_uri(payload)
            row = {
                "page": rel_page,
                "uri": uri,
                "payload": payload,
                "hash": h,
            }
            with queue_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

            seen.add(h)
            result.entities_queued += 1
            if uri:
                result.queued_uris.append(uri)

    _save_seen(root, seen)
    if state is not None:
        state[STATE_KEY] = date.today().isoformat()

    return result


__all__ = [
    "AipFlushResult",
    "AipWatcherResult",
    "STATE_KEY",
    "flush_queue",
    "should_run",
    "run_daily",
]
