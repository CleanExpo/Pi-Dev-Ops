"""swarm/wiki_lint.py — wiki-lint skill implementation.

Weekly health check for the Brain-1 wiki:
  - Orphan pages (in Wiki/ but not in index.md) → auto-fixed
  - Missing cross-refs (plain text mentions of wiki slugs) → auto-fixed
  - Stale pages (updated: date older than decay threshold) → flagged
  - Contradictions (conflicting facts across pages) → flagged via LLM

Public API:
    lint() -> LintReport
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger("swarm.wiki_lint")

# Pages the linter never touches
PROTECTED = {"index.md", "log.md"}

# Pages older than this (days) are always flagged regardless of content
PAGE_STALE_DAYS = 180

# Decay thresholds by keyword (matched against page filename + content)
DECAY_RULES: list[tuple[list[str], int]] = [
    (["competitor", "market", "pricing", "price"], 30),
    (["financial", "metric", "mrr", "arr", "nrr", "revenue"], 90),
    (["regulatory", "compliance", "legal", "ip"], 365),
]


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class LintReport:
    orphans_fixed: list[str] = field(default_factory=list)
    cross_refs_fixed: list[dict] = field(default_factory=list)
    stale_pages: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    log_entry: str = ""
    clean: bool = True
    error: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _today() -> date:
    return datetime.now().date()


def _call_llm(prompt: str) -> str:
    """Gemma 4 (local, zero-cost) → Gemini 3.1 Pro fallback."""
    try:
        from . import ollama_client, config as _cfg  # noqa: PLC0415
        result = ollama_client.chat(
            model=_cfg.OLLAMA_TRIAGE_MODEL,  # gemma4:latest — fast for lint checks
            system="You are a precise knowledge management assistant. Follow instructions exactly.",
            user_message=prompt,
            temperature=0.2,
        )
        if result:
            return result
    except Exception as _exc:  # noqa: BLE001
        log.debug("wiki_lint: gemma4 unavailable (%s) — falling back to Gemini", _exc)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        key_file = Path.home() / ".margot" / "gemini-api-key.txt"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("Gemma 4 unavailable and GEMINI_API_KEY not set")
    from google import genai  # noqa: PLC0415
    model = os.environ.get("MARGOT_TEXT_MODEL", "gemini-3.1-pro-preview-customtools")
    client = genai.Client(api_key=api_key)
    return client.models.generate_content(model=model, contents=prompt).text


def _slugs_from_index(index_content: str) -> set[str]:
    """Extract all [[slug]] references from index.md."""
    return {m.group(1).split("|")[0].strip()
            for m in re.finditer(r'\[\[([^\]]+)\]\]', index_content)}


def _updated_date(content: str) -> date | None:
    """Parse `updated: YYYY-MM-DD` from frontmatter."""
    m = re.search(r'^updated:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return None


def _decay_threshold(filename: str, content: str) -> int:
    """Return the staleness threshold in days for this page."""
    text = (filename + " " + content[:500]).lower()
    for keywords, days in DECAY_RULES:
        if any(kw in text for kw in keywords):
            return days
    return PAGE_STALE_DAYS


# ── Check 1: Orphans ─────────────────────────────────────────────────────────


def _check_orphans(wdir: Path, index_path: Path,
                   index_content: str, all_pages: list[Path]) -> list[str]:
    """Return filenames of pages not referenced in index.md. Auto-fix by adding."""
    indexed = _slugs_from_index(index_content)
    orphans: list[str] = []
    for p in all_pages:
        slug = p.stem
        if slug not in indexed:
            orphans.append(p.name)

    if orphans:
        addition = "\n## Orphaned\n" + "".join(
            f"- [[{Path(f).stem}]] — (orphaned — needs categorisation)\n"
            for f in orphans
        )
        index_path.write_text(index_content + addition, encoding="utf-8")
        log.info("wiki_lint: added %d orphan(s) to index.md", len(orphans))

    return orphans


# ── Check 2: Missing cross-refs ──────────────────────────────────────────────


def _apply_slug(content: str, slug: str) -> tuple[str, int]:
    """Wrap plain-text mentions of slug in [[...]], skipping code spans/blocks."""
    # Split on fenced code blocks (```...```) and inline code (`...`)
    # Odd-indexed parts are code — don't touch them
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', content)
    pattern = r'(?<!\[\[)\b' + re.escape(slug.replace("-", "[ -]")) + r'\b(?!\]\])'
    total = 0
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            new_part, n = re.subn(pattern, f"[[{slug}]]", part, flags=re.IGNORECASE)
            out.append(new_part)
            total += n
    return "".join(out), total


def _check_cross_refs(all_pages: list[Path],
                      all_slugs: set[str]) -> list[dict]:
    """Fix plain-text mentions of wiki slugs that aren't already [[linked]]."""
    fixed: list[dict] = []
    for p in all_pages:
        content = p.read_text(encoding="utf-8")
        replacements = 0
        for slug in all_slugs:
            if slug == p.stem:
                continue
            content, n = _apply_slug(content, slug)
            replacements += n
        if replacements:
            p.write_text(content, encoding="utf-8")
            fixed.append({"page": p.name, "replaced": replacements})
            log.info("wiki_lint: fixed %d cross-ref(s) in %s", replacements, p.name)
    return fixed


# ── Check 3: Stale pages ─────────────────────────────────────────────────────


def _check_stale(all_pages: list[Path]) -> list[dict]:
    """Flag pages whose updated: date exceeds their decay threshold."""
    today = _today()
    stale: list[dict] = []
    for p in all_pages:
        content = p.read_text(encoding="utf-8")
        updated = _updated_date(content)
        if updated is None:
            continue
        threshold = _decay_threshold(p.name, content)
        days_old = (today - updated).days
        if days_old > threshold:
            stale.append({
                "page": p.name,
                "last_updated": updated.isoformat(),
                "days_old": days_old,
                "threshold": threshold,
            })
    return stale


# ── Check 4: Contradictions ──────────────────────────────────────────────────


def _check_contradictions(all_pages: list[Path]) -> list[dict]:
    """Single LLM pass over all pages — find conflicting facts."""
    pages_block = "\n\n".join(
        f"[{p.name}]\n{p.read_text(encoding='utf-8')[:1200]}"
        for p in all_pages
    )
    prompt = (
        "You are auditing a personal knowledge wiki for contradictions. "
        "Read these pages and identify any facts that appear differently "
        "across two or more pages — conflicting dates, numbers, names, "
        "or status claims about the same entity.\n\n"
        f"{pages_block}\n\n"
        "Reply with JSON only (no markdown fences):\n"
        '[{"pages": ["a.md", "b.md"], "fact": "short label", "detail": "what conflicts"}]\n'
        "Return [] if no contradictions found. Be precise — only flag real conflicts, "
        "not different levels of detail about the same fact."
    )
    raw = _call_llm(prompt).strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


# ── Public entry point ───────────────────────────────────────────────────────


def lint() -> LintReport:
    """Run all four wiki health checks. Returns a LintReport.

    Auto-fixes orphans and missing cross-refs. Flags stale pages and
    contradictions for founder review. Always appends to log.md.
    """
    report = LintReport()
    wdir = _wiki_dir()

    if not wdir.exists():
        report.error = f"wiki dir not found: {wdir}"
        report.clean = False
        return report

    index_path = wdir / "index.md"
    if not index_path.exists():
        report.error = "index.md not found"
        report.clean = False
        return report

    index_content = index_path.read_text(encoding="utf-8")
    all_slugs = _slugs_from_index(index_content)
    all_pages = [
        p for p in sorted(wdir.glob("*.md"))
        if p.name not in PROTECTED
    ]

    # 1. Orphans
    try:
        report.orphans_fixed = _check_orphans(
            wdir, index_path, index_content, all_pages
        )
        if report.orphans_fixed:
            index_content = index_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_lint: orphan check failed (%s)", exc)

    # 2. Cross-refs
    try:
        report.cross_refs_fixed = _check_cross_refs(all_pages, all_slugs)
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_lint: cross-ref check failed (%s)", exc)

    # 3. Stale
    try:
        report.stale_pages = _check_stale(all_pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_lint: stale check failed (%s)", exc)

    # 4. Contradictions (LLM — most expensive; runs last)
    try:
        report.contradictions = _check_contradictions(all_pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_lint: contradiction check failed (%s)", exc)

    # Build log entry
    today = _today().isoformat()
    parts = [
        f"{len(report.orphans_fixed)} orphan(s) fixed",
        f"{len(report.cross_refs_fixed)} cross-ref(s) fixed",
        f"{len(report.stale_pages)} stale page(s)",
        f"{len(report.contradictions)} contradiction(s)",
    ]
    report.log_entry = f"{today} | lint | {', '.join(parts)}"
    report.clean = not (report.stale_pages or report.contradictions)

    log_path = wdir / "log.md"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(report.log_entry + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_lint: failed to write log.md (%s)", exc)

    return report


__all__ = ["lint", "LintReport"]
