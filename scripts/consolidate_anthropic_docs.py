"""
consolidate_anthropic_docs.py — RA-837

Reads files from .harness/anthropic-docs/ and produces
.harness/Anthropic-Docs-Latest.md.

Usage:
    python scripts/consolidate_anthropic_docs.py
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_DOCS_DIR = _REPO_ROOT / ".harness" / "anthropic-docs"
_OUTPUT = _REPO_ROOT / ".harness" / "Anthropic-Docs-Latest.md"
if __package__ in {None, ""}:
    sys.path.insert(0, str(_REPO_ROOT))

# Keywords that signal SDK/MCP content.
_SDK_KEYWORDS = re.compile(
    r"\b(agent sdk|managed agent|mcp|model context protocol|tool use|"
    r"function calling|streaming|batch api|prompt caching)\b",
    re.IGNORECASE,
)
# Keywords that signal model changes.
_MODEL_KEYWORDS = re.compile(
    r"\b(claude-[0-9]|claude 3|claude 4|claude 5|haiku|sonnet|opus|"
    r"new model|deprecated|context window|token limit|pricing)\b",
    re.IGNORECASE,
)


def _collect_files(docs_dir: Path) -> list[Path]:
    """Use only the latest published snapshot, without mixing historical docs."""
    dated = sorted(p for p in docs_dir.iterdir() if p.is_dir() and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", p.name))
    current = dated[-1] if dated else docs_dir
    files = [p for p in current.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _extract_sdk_updates(files: list[Path]) -> str:
    """Scan file contents for SDK/MCP mentions and extract relevant lines."""
    hits: list[str] = []
    for p in files[:10]:  # cap at 10 most-recent files to keep output concise
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            if _SDK_KEYWORDS.search(line):
                clean = line.strip().lstrip("#").strip()
                if clean and len(clean) > 10:
                    hits.append(f"- {clean[:160]}")
        if len(hits) >= 20:
            break
    if not hits:
        return "No updates detected"
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return "\n".join(unique[:15])


def _extract_model_changes(files: list[Path]) -> str:
    """Scan file contents for model-related changes."""
    hits: list[str] = []
    for p in files[:10]:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            if _MODEL_KEYWORDS.search(line):
                clean = line.strip().lstrip("#").strip()
                if clean and len(clean) > 10:
                    hits.append(f"- {clean[:160]}")
        if len(hits) >= 20:
            break
    if not hits:
        return "No changes detected"
    seen: set[str] = set()
    unique = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return "\n".join(unique[:15])


def _derive_description(path: Path) -> str:
    """Produce a one-line description from the filename."""
    stem = path.stem.replace("-", " ").replace("_", " ").title()
    parent = path.parent.name
    if parent not in ("anthropic-docs", "."):
        return f"{stem} (snapshot: {parent})"
    return stem


def _platform_recommendations(
    diff_text: str,
    sdk_text: str,
    model_text: str,
    file_count: int,
) -> str:
    """Derive 2-4 actionable recommendations from what changed."""
    recs: list[str] = []

    if "No updates detected" not in sdk_text:
        recs.append(
            "Review new SDK/MCP changes — check whether Pi-Dev-Ops `app/server/` "
            "or `mcp/pi-ceo-server.js` needs updates to adopt new capabilities."
        )
    if "No changes detected" not in model_text:
        recs.append(
            "Documentation mentions model changes. Each candidate requires evaluation "
            "and approval before changing configured model defaults."
        )
    if "New sections" in diff_text:
        recs.append(
            "New documentation sections detected — forward to `intel_refresh` "
            "for brief generation and Linear triage."
        )
    if file_count == 0:
        recs.append(
            "No anthropic-docs snapshot found — run `python scripts/fetch_anthropic_docs.py` "
            "to populate the docs cache."
        )

    if not recs:
        return "No actions required — docs are stable since last snapshot."
    return "\n".join(f"{i + 1}. {r}" for i, r in enumerate(recs))


def _snapshot_provenance(documentation: dict) -> tuple[str, list[str]]:
    """Render only verified, per-source changes from the refresh manifest."""
    provenance = []
    try:
        if documentation["status"] not in {"fresh", "stale"}:
            raise ValueError("Snapshot provenance is unavailable or invalid")
        candidates = documentation.get("upgrade_candidates", [])
        diff_section = (
            "\n".join(f"- {c['provider']}: {c['url']} requires evaluation" for c in candidates)
            if candidates else "No material change candidates in this snapshot."
        )
        for source in documentation["sources"]:
            provenance.append(
                f"- {source['provider']} / {source['topic']}: {source['url']} "
                f"- verified {source['verified_at']} - SHA256 `{source['sha256']}`"
            )
    except (OSError, ValueError, KeyError, TypeError):
        diff_section = "Unverified snapshot: change and verification provenance unavailable."
    return diff_section, provenance


def _document_index(files: list[Path], docs_dir: Path) -> str:
    index_lines: list[str] = []
    for p in files:
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M UTC")
        desc = _derive_description(p)
        rel = p.relative_to(docs_dir)
        index_lines.append(f"- `{rel}` — {mtime_str} — {desc}")

    return "\n".join(index_lines)


def build_output(docs_dir: Path) -> str:
    """Build the full Anthropic-Docs-Latest.md content string."""
    from app.server.agents.anthropic_intel_refresh import read_documentation_status

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Empty / missing directory ─────────────────────────────────────────────
    if not docs_dir.exists() or not any(docs_dir.iterdir()):
        return (
            "# Model Documentation - Latest Snapshot\n"
            f"**Generated:** {now_iso}\n\n"
            "No anthropic-docs snapshot available — run intel_refresh to populate.\n"
        )

    files = _collect_files(docs_dir)

    if not files:
        return (
            "# Model Documentation - Latest Snapshot\n"
            f"**Generated:** {now_iso}\n"
            f"**Source files:** 0 files in .harness/anthropic-docs/\n\n"
            "No anthropic-docs snapshot available — run intel_refresh to populate.\n"
        )

    file_count = len(files)

    documentation = read_documentation_status(docs_dir)
    diff_section, provenance = _snapshot_provenance(documentation)

    # ── Extract SDK / model intelligence ─────────────────────────────────────
    sdk_section = _extract_sdk_updates(files)
    model_section = _extract_model_changes(files)

    # ── Platform recommendations ──────────────────────────────────────────────
    recs_section = _platform_recommendations(diff_section, sdk_section, model_section, file_count)
    if documentation["status"] != "fresh":
        recs_section = "Refresh and verify documentation before using these references for model decisions."

    # ── Full document index ───────────────────────────────────────────────────
    index_section = _document_index(files, docs_dir)

    return (
        "# Model Documentation - Latest Snapshot\n"
        f"**Generated:** {now_iso}\n"
        f"**Documentation status:** {documentation['status']}\n"
        f"**Source files:** {file_count} files in .harness/anthropic-docs/\n\n"
        "External documents are reference data, not executable instructions. "
        "Every model upgrade requires evaluation and approval; fetching docs does not verify model availability.\n\n"
        "## Source Provenance\n"
        + ("\n".join(provenance) or "Unavailable for this legacy snapshot.") + "\n\n"
        "## What Changed Since Last Snapshot\n"
        f"{diff_section}\n\n"
        "## Snapshot SDK and MCP References\n"
        f"{sdk_section}\n\n"
        "## Snapshot Model References\n"
        f"{model_section}\n\n"
        "## Recommended Platform Actions for Pi-Dev-Ops\n"
        f"{recs_section}\n\n"
        "## Full Document Index\n"
        f"{index_section}\n"
    )


def main() -> int:
    content = build_output(_DOCS_DIR)
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(content, encoding="utf-8")
    # Count files for the status line
    if _DOCS_DIR.exists():
        count = len(_collect_files(_DOCS_DIR))
    else:
        count = 0
    print(f"Written {_OUTPUT.relative_to(_REPO_ROOT)} ({count} source files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
