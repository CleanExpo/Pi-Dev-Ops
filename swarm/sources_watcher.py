"""swarm/sources_watcher.py — auto-ingest new Brain-1 Sources/ clips.

Runs every orchestrator cycle. Diffs Sources/*.md against the processed
log; any new file gets ingested immediately. Zero LLM cost when nothing
is new — pure filesystem diff.

Public API:
    run_cycle() -> WatcherResult
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("swarm.sources_watcher")

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_LOG_REL = ".harness/sources_processed.jsonl"


@dataclass
class WatcherResult:
    ingested: list[str] = field(default_factory=list)
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _processed_log(repo_root: Path) -> Path:
    p = repo_root / PROCESSED_LOG_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_processed(log_path: Path) -> set[str]:
    """Return set of filenames already ingested (stem only, for rename-safety)."""
    if not log_path.exists():
        return set()
    seen: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("status") == "ok":
                seen.add(row["filename"])
        except (json.JSONDecodeError, KeyError):
            continue
    return seen


def _sources_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR).parent / "Sources"


def _completed_dir() -> Path:
    d = _sources_dir() / "Completed"
    d.mkdir(exist_ok=True)
    return d


def run_cycle(repo_root: Path | None = None) -> WatcherResult:
    """Check Sources/ for new clips and ingest them.

    Safe to call every orchestrator cycle — returns immediately when
    there is nothing new (pure filesystem stat, no LLM).
    """
    rr = repo_root or REPO_ROOT

    result = WatcherResult()
    sources = _sources_dir()
    if not sources.exists():
        return result

    log_path = _processed_log(rr)
    processed = _load_processed(log_path)

    new_files = [
        p for p in sorted(sources.glob("*.md"))
        if p.name not in processed
    ]

    if not new_files:
        return result

    from .wiki_ingest import ingest_file  # noqa: PLC0415

    for p in new_files:
        try:
            ingest_result = ingest_file(p)
            row = {
                "filename": p.name,
                "path": str(p),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "status": ingest_result.status,
                "pages_updated": ingest_result.pages_updated,
                "pages_created": ingest_result.pages_created,
                "error": ingest_result.error,
            }
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

            if ingest_result.status == "ok":
                result.ingested.append(p.name)
                log.info("sources_watcher: ingested %s → updated %s",
                         p.name, ingest_result.pages_updated)
                # Move to Completed/ — keeps Sources/ clean, still retrievable
                try:
                    dest = _completed_dir() / p.name
                    p.rename(dest)
                    log.info("sources_watcher: moved %s → Completed/", p.name)
                except Exception as mv_exc:  # noqa: BLE001
                    log.warning("sources_watcher: move failed for %s (%s)",
                                p.name, mv_exc)
            else:
                result.errors.append(f"{p.name}: {ingest_result.error}")
                log.warning("sources_watcher: ingest failed for %s — %s (left in Sources/)",
                            p.name, ingest_result.error)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{p.name}: {exc}")
            log.warning("sources_watcher: error on %s (%s)", p.name, exc)

    result.skipped = len(processed)
    return result


@dataclass
class DrainResult:
    written: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _safe_destination(filename: str, sources: Path) -> Path | None:
    """The path this row may be written to, or None if it may not be written.

    RE-VALIDATED HERE, not trusted from the row. `routes/wiki_sources.py`
    validates the filename before insert, but this function is what actually
    touches a filesystem, and a check performed by a different process at a
    different time is a claim rather than a guarantee — the table could be
    written by a future caller, a migration, or by hand.

    Two independent checks, because either alone has a hole: the name must match
    the guard's allowlist AND the resolved path must still be inside `Sources/`.
    The second catches anything the first's regex did not anticipate.
    """
    from .ingest_guard import PROTECTED_PAGES, SAFE_NAME  # noqa: PLC0415

    name = (filename or "").strip()
    if not name or not SAFE_NAME.match(name) or name in PROTECTED_PAGES:
        return None
    dest = (sources / name).resolve()
    if dest.parent != sources.resolve():
        return None
    return dest


def pull_staging(limit: int = 20) -> DrainResult:
    """Drain `wiki_source_staging` into `Sources/` on the brain host.

    The other half of the knowledge front door: `POST /api/wiki/sources/upload`
    accepts a document from anywhere into Supabase, and this — running only
    where the vault actually lives — turns those rows into files that
    `run_cycle()` then ingests on its normal pass.

    A row whose filename cannot be re-validated is marked `quarantined` and left
    on disk-untouched: refusing to write it is the whole point, and deleting it
    would destroy the evidence of what was attempted.
    """
    from app.server import wiki_source_store  # noqa: PLC0415

    result = DrainResult()
    rows = wiki_source_store.queued_sources(limit)
    if not rows:
        return result
    sources = _sources_dir()
    sources.mkdir(parents=True, exist_ok=True)

    for row in rows:
        sid = str(row.get("id") or "")
        dest = _safe_destination(str(row.get("filename") or ""), sources)
        if dest is None:
            wiki_source_store.mark_source(sid, "quarantined", "filename failed re-validation")
            result.quarantined.append(sid[:12])
            log.warning("pull_staging: quarantined %s — filename failed re-validation", sid[:12])
            continue
        try:
            dest.write_text(str(row.get("body_md") or ""), encoding="utf-8")
        except OSError as exc:
            wiki_source_store.mark_source(sid, "error", f"write failed: {exc}")
            result.errors.append(f"{sid[:12]}: {exc}")
            continue
        wiki_source_store.mark_source(sid, "ingested", None)
        result.written.append(dest.name)
        log.info("pull_staging: wrote %s from staging row %s", dest.name, sid[:12])
    return result


__all__ = ["run_cycle", "WatcherResult", "pull_staging", "DrainResult"]
