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


__all__ = ["run_cycle", "WatcherResult"]
