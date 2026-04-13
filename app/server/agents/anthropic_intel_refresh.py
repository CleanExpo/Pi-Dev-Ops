"""
anthropic_intel_refresh.py — Anthropic Intelligence Refresh Loop (RA-TBD)

Periodically fetches current Anthropic documentation, diffs against snapshot,
and alerts when material changes detected (SDK, hooks, models, context, tools).

Usage:
    python -m app.server.agents.anthropic_intel_refresh [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("pi-ceo.agents.anthropic-intel-refresh")

# ─── paths ────────────────────────────────────────────────────────────────────

_HARNESS = Path(__file__).parent.parent.parent.parent / ".harness"
_SNAPSHOT_ROOT = _HARNESS / "anthropic-docs"
_BRIEF_ROOT = _HARNESS / "board-meetings"

# ─── URLs to fetch ────────────────────────────────────────────────────────────

_DOCS_URLS = [
    "https://docs.claude.com/en/release-notes/overview",
    "https://docs.claude.com/en/api/overview",
    "https://docs.claude.com/en/docs/claude-code/overview",
]

# ─── keywords flagging re-exam ────────────────────────────────────────────────

_MATERIAL_KEYWORDS = {
    "agent sdk", "subagent", "hook", "tool", "mcp",
    "context", "model", "release", "breaking", "change",
    "deprecat", "new feature", "update", "improvements",
}


async def refresh_anthropic_intel(
    snapshot_dir: str = ".harness/anthropic-docs",
    brief_dir: str = ".harness/board-meetings",
    dry_run: bool = False,
) -> dict:
    """Fetch current Anthropic docs, diff against snapshot, write brief on delta.

    Returns a dict with:
        - fetched_urls: list of URLs successfully fetched
        - new_snapshot_path: dated folder under snapshot_dir
        - delta_summary: dict mapping filename -> {added, removed, changed} line counts
        - brief_path: path to written board brief, or None if no delta
        - errors: list of (url, error_message) tuples
    """
    snapshot_root = Path(snapshot_dir)
    brief_root = Path(brief_dir)

    # Create directories if they don't exist
    if not dry_run:
        snapshot_root.mkdir(parents=True, exist_ok=True)
        brief_root.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_snapshot_path = snapshot_root / today

    # Fetch all URLs
    fetched_content: dict[str, str] = {}
    errors: list[tuple[str, str]] = []
    fetched_urls: list[str] = []

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in _DOCS_URLS:
            try:
                response = await client.get(url)
                response.raise_for_status()
                fetched_content[url] = response.text
                fetched_urls.append(url)
            except httpx.HTTPError as e:
                errors.append((url, str(e)))
            except Exception as e:
                errors.append((url, f"Unexpected error: {str(e)}"))

    # Extract filenames from URLs (use path segments to ensure uniqueness)
    url_to_filename = {}
    for url in fetched_content:
        # Use last two path segments to avoid collisions
        # e.g., "release-notes/overview" -> "release-notes-overview.md"
        path_parts = url.rstrip("/").split("/")
        if len(path_parts) >= 2:
            # Last two segments
            segment = "-".join(path_parts[-2:])
        else:
            segment = path_parts[-1]
        filename = f"{segment}.md" if not segment.endswith(".md") else segment
        url_to_filename[url] = filename

    # Compute delta against most recent prior snapshot
    delta_summary: dict[str, dict[str, int]] = {}
    prior_snapshot_path: Path | None = None

    if snapshot_root.exists():
        # Find most recent prior snapshot (alphabetical sort of YYYY-MM-DD)
        prior_dirs = sorted([d for d in snapshot_root.iterdir() if d.is_dir()])
        if prior_dirs:
            prior_snapshot_path = prior_dirs[-1]

    for url, content in fetched_content.items():
        filename = url_to_filename[url]
        new_lines = content.splitlines()
        new_line_count = len(new_lines)

        if prior_snapshot_path:
            prior_file = prior_snapshot_path / filename
            if prior_file.exists():
                prior_content = prior_file.read_text()
                prior_lines = prior_content.splitlines()
                prior_line_count = len(prior_lines)

                # Simple diff: count changes
                added = max(0, new_line_count - prior_line_count)
                removed = max(0, prior_line_count - new_line_count)
                changed = 1 if prior_content != content else 0

                delta_summary[filename] = {
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                }
            else:
                # Prior snapshot missing this file
                delta_summary[filename] = {
                    "added": new_line_count,
                    "removed": 0,
                    "changed": 1,
                }
        else:
            # No prior snapshot — treat as baseline
            pass

    # Determine if there is material delta
    has_delta = bool(delta_summary) and any(
        d.get("changed", 0) == 1 or d.get("added", 0) > 5
        for d in delta_summary.values()
    )

    brief_path: str | None = None

    if has_delta and prior_snapshot_path and delta_summary:
        # Build brief
        brief_name = f"anthropic-intel-refresh-{today}.md"
        brief_file = brief_root / brief_name
        brief_path = str(brief_file)

        # Check for material keywords in added content
        added_preview: dict[str, list[str]] = {}
        material_found = False

        for url, content in fetched_content.items():
            filename = url_to_filename[url]
            new_lines = content.splitlines()

            # Get first 10 lines of added content (approximation)
            preview_lines = []
            for line in new_lines[:20]:
                if any(kw in line.lower() for kw in _MATERIAL_KEYWORDS):
                    preview_lines.append(line)
                    material_found = True
                if len(preview_lines) >= 10:
                    break

            if preview_lines:
                added_preview[filename] = preview_lines

        # Recommendation
        recommendation = (
            "Re-examine Pi-CEO architecture — material changes detected"
            if material_found
            else "No material changes require architecture review"
        )

        # Write brief
        brief_content = f"""# Anthropic Intelligence Refresh — {today}

## Summary

Fetched {len(fetched_urls)} documentation URLs. Delta detected against snapshot from {prior_snapshot_path.name}.

## Delta Summary

"""
        for filename, delta in delta_summary.items():
            brief_content += f"- **{filename}**: +{delta['added']} -{delta['removed']} ~{delta['changed']}\n"

        brief_content += "\n## Added Content Preview\n\n"
        for filename, lines in added_preview.items():
            brief_content += f"### {filename}\n\n```\n"
            brief_content += "\n".join(lines[:10])
            brief_content += "\n```\n\n"

        brief_content += f"## Recommendation\n\n{recommendation}\n"

        if not dry_run:
            brief_file.write_text(brief_content)
            log.info("Wrote brief to %s", brief_file)

    # Write new snapshot
    if not dry_run and fetched_content:
        new_snapshot_path.mkdir(parents=True, exist_ok=True)
        for url, content in fetched_content.items():
            filename = url_to_filename[url]
            snapshot_file = new_snapshot_path / filename
            snapshot_file.write_text(content)
            log.info("Wrote snapshot to %s", snapshot_file)

    return {
        "fetched_urls": fetched_urls,
        "new_snapshot_path": str(new_snapshot_path),
        "delta_summary": delta_summary,
        "brief_path": brief_path,
        "errors": errors,
    }


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """Run refresh with CLI args."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Fetch and diff Anthropic docs against snapshot."
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
