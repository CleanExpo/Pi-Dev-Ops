"""
consolidate_anthropic_docs.py — RA-837

Reads files from .harness/anthropic-docs/ and produces
.harness/Anthropic-Docs-Latest.md.

Usage:
    python scripts/consolidate_anthropic_docs.py
"""
import difflib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_DOCS_DIR = _REPO_ROOT / ".harness" / "anthropic-docs"
_OUTPUT = _REPO_ROOT / ".harness" / "Anthropic-Docs-Latest.md"

# Markdown heading pattern — used to extract section names for diff summary.
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)", re.MULTILINE)

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
    """Return all .md files in docs_dir (including subdirectories), sorted newest-first."""
    files = [p for p in docs_dir.rglob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _read_index(docs_dir: Path) -> dict:
    idx_path = docs_dir / "index.json"
    if idx_path.exists():
        try:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _extract_sections(text: str) -> list[str]:
    return _HEADING_RE.findall(text)


def _diff_summary(old_text: str, new_text: str) -> str:
    """Produce a human-readable diff summary between two document texts."""
    old_sections = set(_extract_sections(old_text))
    new_sections = set(_extract_sections(new_text))

    added = sorted(new_sections - old_sections)
    removed = sorted(old_sections - new_sections)

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=0))
    # Count changed lines (added/removed in diff body, ignoring headers)
    added_lines = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
    removed_lines = [l for l in diff if l.startswith("-") and not l.startswith("---")]

    parts: list[str] = []
    if added:
        parts.append("**New sections:** " + ", ".join(f"`{s}`" for s in added[:10]))
    if removed:
        parts.append("**Removed sections:** " + ", ".join(f"`{s}`" for s in removed[:10]))
    if added_lines or removed_lines:
        parts.append(
            f"**Line changes:** +{len(added_lines)} / -{len(removed_lines)} lines across all files"
        )
    return "\n".join(parts) if parts else "No structural changes detected."


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
            "Model availability has changed — update `.harness/config.yaml` "
            "default model references if newer Claude versions are now preferred."
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


def build_output(docs_dir: Path) -> str:
    """Build the full Anthropic-Docs-Latest.md content string."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Empty / missing directory ─────────────────────────────────────────────
    if not docs_dir.exists() or not any(docs_dir.iterdir()):
        return (
            "# Anthropic Docs — Latest Snapshot\n"
            f"**Generated:** {now_iso}\n\n"
            "No anthropic-docs snapshot available — run intel_refresh to populate.\n"
        )

    files = _collect_files(docs_dir)

    if not files:
        return (
            "# Anthropic Docs — Latest Snapshot\n"
            f"**Generated:** {now_iso}\n"
            f"**Source files:** 0 files in .harness/anthropic-docs/\n\n"
            "No anthropic-docs snapshot available — run intel_refresh to populate.\n"
        )

    file_count = len(files)

    # ── Diff: compare the two most-recent files ───────────────────────────────
    if file_count >= 2:
        try:
            newest_text = files[0].read_text(encoding="utf-8", errors="replace")
            prev_text = files[1].read_text(encoding="utf-8", errors="replace")
            diff_section = _diff_summary(prev_text, newest_text)
        except Exception as exc:
            diff_section = f"Diff unavailable: {exc}"
    else:
        diff_section = "First snapshot — full index below"

    # ── Extract SDK / model intelligence ─────────────────────────────────────
    sdk_section = _extract_sdk_updates(files)
    model_section = _extract_model_changes(files)

    # ── Platform recommendations ──────────────────────────────────────────────
    recs_section = _platform_recommendations(diff_section, sdk_section, model_section, file_count)

    # ── Full document index ───────────────────────────────────────────────────
    index_lines: list[str] = []
    for p in files:
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M UTC")
        desc = _derive_description(p)
        rel = p.relative_to(docs_dir)
        index_lines.append(f"- `{rel}` — {mtime_str} — {desc}")

    index_section = "\n".join(index_lines)

    return (
        "# Anthropic Docs — Latest Snapshot\n"
        f"**Generated:** {now_iso}\n"
        f"**Source files:** {file_count} files in .harness/anthropic-docs/\n\n"
        "## What Changed Since Last Snapshot\n"
        f"{diff_section}\n\n"
        "## New SDK Features & MCP Updates\n"
        f"{sdk_section}\n\n"
        "## Model Additions / Changes\n"
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
        count = len([p for p in _DOCS_DIR.rglob("*.md") if p.is_file()])
    else:
        count = 0
    print(f"Written {_OUTPUT.relative_to(_REPO_ROOT)} ({count} source files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
