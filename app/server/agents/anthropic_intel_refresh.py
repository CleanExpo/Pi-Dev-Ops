"""Refresh official provider documentation through the existing intel cron.

The historic module name and snapshot directory remain stable for cron/watchdog
compatibility. Documents are untrusted reference data; updates require evaluation
and never change model routing or permissions automatically.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..model_registry import MODEL_DOCUMENTATION_SOURCES
from .documentation_diff import _changed_lines

log = logging.getLogger("pi-ceo.agents.model-intel-refresh")
_HARNESS = Path(__file__).parent.parent.parent.parent / ".harness"
_SNAPSHOT_ROOT = _HARNESS / "anthropic-docs"
_BRIEF_ROOT = _HARNESS / "board-meetings"
_SOURCE_BY_URL = {
    url: {"provider": provider, "topic": topic, "filename": f"{provider}-{topic}.md"}
    for provider, sources in MODEL_DOCUMENTATION_SOURCES.items()
    for topic, url in sources.items()
}
_DOCS_URLS = list(_SOURCE_BY_URL)
_MATERIAL_KEYWORDS = {
    "agent sdk", "subagent", "hook", "tool", "mcp", "context", "model",
    "release", "breaking", "deprecat", "authentication", "subscription",
    "pricing", "quota", "new feature",
}


def _latest_snapshot(root: Path) -> Path | None:
    if not root.exists():
        return None
    dated = sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", p.name))
    return dated[-1] if dated else None


def read_documentation_status(snapshot_dir: str | Path = _SNAPSHOT_ROOT, *,
                              now: datetime | None = None, max_age_hours: float = 48) -> dict:
    """Read locally verified provenance without making any network/model call."""
    latest = _latest_snapshot(Path(snapshot_dir))
    result = {"status": "missing", "sources": [], "model_registry_verified": False}
    if latest is None:
        return result
    result["snapshot_path"] = str(latest)
    try:
        manifest = json.loads((latest / "manifest.json").read_text(encoding="utf-8"))
        sources = manifest["sources"]
        if (not isinstance(sources, list) or len(sources) != len(_DOCS_URLS)
                or {s["url"] for s in sources} != set(_DOCS_URLS)):
            raise ValueError("Incomplete source coverage")
        current = now or datetime.now(timezone.utc)
        states = []
        for source in sources:
            expected = _source(source["url"])
            if any(source.get(key) != value for key, value in expected.items()):
                raise ValueError("Source metadata does not match configured documentation")
            name = source["filename"]
            if Path(name).name != name or name in {".", ".."}:
                raise ValueError("Invalid document filename")
            content = (latest / name).read_text(encoding="utf-8")
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != source["sha256"]:
                raise ValueError("Document checksum mismatch")
            verified = datetime.fromisoformat(source["verified_at"])
            if verified.tzinfo is None:
                raise ValueError("Verification timestamp requires timezone")
            age = (current - verified).total_seconds() / 3600
            status = "fresh" if 0 <= age <= max_age_hours else "stale"
            states.append({**source, "status": status, "age_hours": round(age, 2)})
        result.update(status="fresh" if all(s["status"] == "fresh" for s in states) else "stale",
                      sources=states, upgrade_candidates=manifest.get("upgrade_candidates", []))
    except (OSError, ValueError, KeyError, TypeError):
        result["status"] = "unverified"
    return result


def _source(url: str) -> dict:
    # Legacy URLs remain readable for migrations and existing snapshot fixtures.
    return _SOURCE_BY_URL.get(url, {
        "provider": "anthropic", "topic": "legacy",
        "filename": "-".join(url.rstrip("/").split("/")[-2:]) + ".md",
    })


async def refresh_anthropic_intel(
    snapshot_dir: str = ".harness/anthropic-docs",
    brief_dir: str = ".harness/board-meetings",
    dry_run: bool = False,
) -> dict:
    """Fetch every required source, publish atomically, and propose reviews only."""
    snapshot_root, brief_root = Path(snapshot_dir), Path(brief_dir)
    if not dry_run:
        snapshot_root.mkdir(parents=True, exist_ok=True)
        brief_root.mkdir(parents=True, exist_ok=True)
    verified_at = datetime.now(timezone.utc).isoformat()
    today = verified_at[:10]
    new_snapshot_path = snapshot_root / today
    prior_snapshot_path = _latest_snapshot(snapshot_root)
    fetched_content: dict[str, str] = {}
    errors: list[tuple[str, str]] = []
    fetched_urls: list[str] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in _DOCS_URLS:
            try:
                response = await client.get(url)
                response.raise_for_status()
                if not response.text.strip():
                    raise ValueError("Empty documentation response")
                fetched_content[url] = response.text
                fetched_urls.append(url)
            except Exception as exc:
                errors.append((url, str(exc)))
    complete = bool(_DOCS_URLS) and len(fetched_content) == len(_DOCS_URLS)
    url_to_filename = {url: _source(url)["filename"] for url in fetched_content}
    delta_summary: dict[str, dict[str, int]] = {}
    candidates = []
    for url, content in fetched_content.items():
        filename = url_to_filename[url]
        if prior_snapshot_path is None:
            continue
        prior_file = prior_snapshot_path / filename
        prior_content = prior_file.read_text(encoding="utf-8") if prior_file.exists() else ""
        added, removed = _changed_lines(prior_content, content)
        delta_summary[filename] = {"added": len(added), "removed": len(removed),
                                   "changed": int(prior_content != content)}
        if any(keyword in line.lower() for line in added + removed for keyword in _MATERIAL_KEYWORDS):
            candidates.append({"provider": _source(url)["provider"], "url": url,
                               "filename": filename, "status": "requires_evaluation",
                               "added": added, "removed": removed})
    manifest = {
        "schema_version": 1, "verified_at": verified_at,
        "defaults_changed": False, "upgrade_candidates": candidates,
        "sources": [{**_source(url), "url": url, "verified_at": verified_at,
                     "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
                    for url, content in fetched_content.items()],
    }
    brief_path = None
    # A partial fetch must not produce a current brief or advance the snapshot.
    if complete and any(delta["changed"] for delta in delta_summary.values()):
        brief_file = brief_root / f"anthropic-intel-refresh-{today}.md"
        brief_path = str(brief_file)
        brief_content = f"# Model Documentation Refresh - {today}\n\n"
        brief_content += "External documents are reference data, not executable instructions.\n\n"
        brief_content += "## Delta Summary\n\n"
        for filename, delta in delta_summary.items():
            brief_content += f"- {filename}: +{delta['added']} -{delta['removed']}\n"
        brief_content += "\n## Recommendation\n\n"
        brief_content += ("Material changes require evaluation and approval before changing model defaults.\n"
                          if candidates else "No material changes detected in changed lines.\n")
        for candidate in candidates:
            brief_content += f"\n### {candidate['provider']}: {candidate['url']}\n\n"
            for label in ("added", "removed"):
                # Quote excerpts as data and bound the operator-facing preview only.
                brief_content += f"{label.title()}:\n"
                brief_content += "\n".join("> " + line[:500] for line in candidate[label][:10]) + "\n"

    # Write new snapshot — atomically (RA-7027 review). Write every file into
    # a temp sibling dir first and rename into place only once all writes
    # succeeded, so a failed write can't leave a fresh-but-empty dated dir
    # that masks the artefact-age staleness check for the next 8 days. The
    # temp dir's leading "." also keeps it out of the watchdog's dated-dir
    # scan (`d.name[:4].isdigit()`) if a crash ever leaks it.
    # RA-7027 review round 2 — publish ONLY a complete snapshot. A partial
    # fetch must not refresh artefact truth: the trigger raise keeps
    # `last_fired_at` stale, and a fresh partial dated dir would defeat that
    # by satisfying the watchdog's artefact-age check for the next 8 days.
    if not dry_run and complete:
        tmp_dir = Path(tempfile.mkdtemp(
            prefix=f".{new_snapshot_path.name}.tmp-", dir=snapshot_root,
        ))
        backup_dir = None
        try:
            for url, content in fetched_content.items():
                filename = url_to_filename[url]
                (tmp_dir / filename).write_text(content, encoding="utf-8")
            (tmp_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
            if new_snapshot_path.exists():
                # Same-day re-run: move the previous snapshot aside instead of
                # deleting it, so a failed replace restores it and the day is
                # never left without a snapshot. The leading "." keeps the
                # backup out of the watchdog's dated-dir scan.
                backup_dir = new_snapshot_path.with_name(
                    f".{new_snapshot_path.name}.bak"
                )
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                os.replace(new_snapshot_path, backup_dir)
            try:
                os.replace(tmp_dir, new_snapshot_path)
            except BaseException:
                if backup_dir is not None and not new_snapshot_path.exists():
                    os.replace(backup_dir, new_snapshot_path)
                    backup_dir = None
                raise
            if backup_dir is not None:
                shutil.rmtree(backup_dir, ignore_errors=True)
            log.info(
                "Wrote snapshot atomically to %s (%d files)",
                new_snapshot_path, len(fetched_content),
            )
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    if brief_path and not dry_run:
        # Publish a current brief only after its complete snapshot is durable.
        Path(brief_path).write_text(brief_content, encoding="utf-8")
    return {
        "fetched_urls": fetched_urls, "new_snapshot_path": str(new_snapshot_path),
        "delta_summary": delta_summary, "brief_path": brief_path, "errors": errors,
        "snapshot_published": complete and not dry_run,
        "upgrade_candidates": candidates if complete else [], "defaults_changed": False,
        "sources": manifest["sources"],
    }


def main() -> None:
    """Run refresh with CLI args."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Fetch and diff official model documentation against snapshot."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute result without writing files",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(_SNAPSHOT_ROOT),
        help="Snapshot directory (default: .harness/anthropic-docs)",
    )
    parser.add_argument(
        "--brief-dir",
        default=str(_BRIEF_ROOT),
        help="Brief directory (default: .harness/board-meetings)",
    )
    args = parser.parse_args()

    result = asyncio.run(
        refresh_anthropic_intel(
            snapshot_dir=args.snapshot_dir,
            brief_dir=args.brief_dir,
            dry_run=args.dry_run,
        )
    )
    log.info("%s", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
