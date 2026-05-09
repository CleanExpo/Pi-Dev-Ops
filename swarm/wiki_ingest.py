"""swarm/wiki_ingest.py — wiki-ingest skill implementation.

Writes a research finding, Board output, or Margot insight back into the
Brain-1 wiki at BRAIN1_WIKI_DIR. Updates existing pages, creates new ones,
appends to log.md, re-uploads changed files to Gemini corpus.

Public API:
    ingest(finding, source_type, topic, turn_id) -> IngestResult
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.wiki_ingest")

MAX_PAGES_PER_INGEST = 10
MAX_FINDING_CHARS = 8000


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    status: str = "ok"
    pages_updated: list[str] = field(default_factory=list)
    pages_created: list[str] = field(default_factory=list)
    log_entry: str = ""
    corpus_synced: bool = False
    error: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")  # local date


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _load_index(wdir: Path) -> str:
    p = wdir / "index.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _call_llm(prompt: str) -> str:
    """Gemma 4 (local, zero-cost) → Gemini 3.1 Pro fallback."""
    # ── Primary: Gemma 4 via Ollama (free) ───────────────────────────────────
    try:
        from . import ollama_client, config as _cfg  # noqa: PLC0415
        result = ollama_client.chat(
            model=_cfg.OLLAMA_TRIAGE_MODEL,  # gemma4:latest — fast for ingest
            system="You are a precise knowledge management assistant. Follow instructions exactly.",
            user_message=prompt,
            temperature=0.2,
        )
        if result:
            return result
    except Exception as _exc:  # noqa: BLE001
        log.debug("wiki_ingest: gemma4 unavailable (%s) — falling back to Gemini", _exc)

    # ── Fallback: Gemini 3.1 Pro ─────────────────────────────────────────────
    from pathlib import Path as _Path  # noqa: PLC0415
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        key_file = _Path.home() / ".margot" / "gemini-api-key.txt"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("Gemma 4 unavailable and GEMINI_API_KEY not set")

    from google import genai  # noqa: PLC0415
    import concurrent.futures  # noqa: PLC0415
    text_model = os.environ.get("MARGOT_TEXT_MODEL", "gemini-3.1-pro-preview-customtools")
    client = genai.Client(api_key=api_key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(
            lambda: client.models.generate_content(model=text_model, contents=prompt).text
        ).result(timeout=90)


def _identify_targets(finding: str, index: str) -> dict[str, Any]:
    """Ask LLM which pages to update and whether a new page is needed."""
    prompt = (
        "You are updating a personal knowledge wiki. Given the finding below "
        "and the wiki index, identify which pages to update.\n\n"
        f"Wiki index:\n{index}\n\n"
        f"Finding:\n{finding}\n\n"
        "Reply with JSON only (no markdown fences):\n"
        '{"update": ["filename.md", ...], '
        '"create": {"slug": "new-page-slug", "description": "one-line", "section": "## Section"} | null}\n'
        "Rules: update ≤5 files. create is null if no new page is needed. "
        "Only name files that actually appear in the index. "
        "NEVER include index.md or log.md — those are managed by the system."
    )
    raw = _call_llm(prompt).strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"update": [], "create": None}


def _merge_page(page_content: str, finding: str, today: str) -> str:
    """Ask LLM to merge the finding into an existing page."""
    prompt = (
        "Merge the finding into this wiki page. Rules:\n"
        "- Add new facts; update changed ones; never delete existing facts.\n"
        "- If a claim changes, overwrite it and add an inline note: "
        f"<!-- updated {today}: previously said X -->\n"
        "- Preserve all [[double-bracket]] cross-refs. Add new ones if relevant.\n"
        "- Update the frontmatter `updated:` date to today.\n"
        "- No filler sentences. Every sentence carries information.\n"
        "- Return the complete updated page content only — no explanation.\n\n"
        f"Today: {today}\n\n"
        f"Current page:\n{page_content}\n\n"
        f"Finding to merge:\n{finding}"
    )
    return _call_llm(prompt).strip()


def _write_new_page(slug: str, finding: str, today: str) -> str:
    """Ask LLM to write a new wiki page for this finding."""
    prompt = (
        f"Write a new wiki page about: {slug}\n\n"
        "Use this frontmatter:\n"
        f"---\ntype: wiki\nupdated: {today}\n---\n\n"
        "Rules:\n"
        "- Concise. No filler. Every sentence carries information.\n"
        "- Use [[double-bracket]] links to other wiki pages where relevant.\n"
        "- End with a ## Cross-refs section listing related pages.\n"
        "- Return the complete page content only — no explanation.\n\n"
        f"Source finding:\n{finding}"
    )
    return _call_llm(prompt).strip()


def _append_to_index(index_content: str, slug: str,
                     description: str, section: str) -> str:
    """Insert a new page entry under the correct section in index.md."""
    line = f"- [[{slug}]] — {description}"
    if section and section in index_content:
        return index_content.replace(
            section,
            f"{section}\n{line}",
            1,
        )
    return index_content + f"\n{line}\n"


def _corpus_reupload(changed_files: list[Path]) -> bool:
    """Re-upload changed wiki files to the Gemini File Search store."""
    from . import config  # noqa: PLC0415
    store_name = config.MARGOT_FILE_SEARCH_STORE
    if not store_name:
        # Try loading from ~/.margot/.env (standalone runs without server env)
        env_file = Path.home() / ".margot" / ".env"
        if env_file.exists():
            for _line in env_file.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if _line.startswith("MARGOT_FILE_SEARCH_STORE="):
                    store_name = _line.split("=", 1)[1].strip()
                    break
    if not store_name:
        log.debug("wiki_ingest: MARGOT_FILE_SEARCH_STORE unset — skipping corpus upload")
        return False
    try:
        key_file = Path.home() / ".margot" / "gemini-api-key.txt"
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key and key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
        if not api_key:
            log.warning("wiki_ingest: no Gemini API key — skipping corpus upload")
            return False

        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
        client = genai.Client(api_key=api_key)

        existing: set[str] = set()
        try:
            for doc in client.file_search_stores.documents.list(parent=store_name):
                if doc.display_name:
                    existing.add(doc.display_name)
        except Exception as exc:  # noqa: BLE001
            log.warning("wiki_ingest: could not list corpus docs (%s) — uploading all", exc)

        for f in changed_files:
            client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=store_name,
                file=f,
                config=types.UploadToFileSearchStoreConfig(
                    display_name=f.name,
                    mime_type="text/plain",
                ),
            )
            log.info("wiki_ingest: uploaded %s to corpus", f.name)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_ingest: corpus re-upload failed (%s) — local wiki is still updated", exc)
        return False


# ── Public entry point ───────────────────────────────────────────────────────


def ingest(finding: str, source_type: str = "research",
           topic: str = "", turn_id: str = "") -> IngestResult:
    """Ingest a finding into the Brain-1 wiki.

    Args:
        finding:     The text to ingest (research summary, Board output, etc.)
        source_type: "research" | "board" | "board_trigger" | "manual"
        topic:       Short label for log.md (optional)
        turn_id:     Links back to a Margot turn or Board session (optional)

    Returns:
        IngestResult with pages_updated, pages_created, log_entry, corpus_synced.
    """
    result = IngestResult()
    wdir = _wiki_dir()

    if not wdir.exists():
        result.status = "error"
        result.error = f"wiki dir not found: {wdir}"
        return result

    finding = finding[:MAX_FINDING_CHARS]
    today = _now_date()
    changed: list[Path] = []

    try:
        index = _load_index(wdir)
        targets = _identify_targets(finding, index)
    except Exception as exc:  # noqa: BLE001
        result.status = "error"
        result.error = f"target identification failed: {exc}"
        return result

    # ── Update existing pages ─────────────────────────────────────────────
    protected = {"index.md", "log.md"}
    for filename in (targets.get("update") or [])[:MAX_PAGES_PER_INGEST]:
        if not filename.endswith(".md"):
            filename = filename + ".md"
        if filename in protected:
            continue
        p = wdir / filename
        if not p.exists():
            log.warning("wiki_ingest: target page %s not found — skipping", filename)
            continue
        try:
            updated = _merge_page(p.read_text(encoding="utf-8"), finding, today)
            p.write_text(updated, encoding="utf-8")
            result.pages_updated.append(filename)
            changed.append(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("wiki_ingest: failed to update %s (%s)", filename, exc)

    # ── Create new page if warranted ──────────────────────────────────────
    new_page = targets.get("create")
    if new_page and isinstance(new_page, dict):
        slug = new_page.get("slug", "").strip()
        description = new_page.get("description", "").strip()
        section = new_page.get("section", "").strip()
        if slug:
            filename = f"{slug}.md"
            p = wdir / filename
            try:
                content = _write_new_page(slug, finding, today)
                p.write_text(content, encoding="utf-8")
                result.pages_created.append(filename)
                changed.append(p)

                index_path = wdir / "index.md"
                if index_path.exists():
                    updated_index = _append_to_index(
                        index_path.read_text(encoding="utf-8"),
                        slug, description, section,
                    )
                    index_path.write_text(updated_index, encoding="utf-8")
                    if index_path not in changed:
                        changed.append(index_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("wiki_ingest: failed to create %s (%s)", filename, exc)

    # ── Append to log.md ──────────────────────────────────────────────────
    all_touched = result.pages_updated + result.pages_created
    label = topic or source_type
    log_line = (
        f"{today} | ingest | {', '.join(all_touched) or 'none'} | "
        f"{label}"
        + (f" (turn {turn_id})" if turn_id else "")
    )
    log_path = wdir / "log.md"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(log_line + "\n")
        result.log_entry = log_line
        if log_path not in changed:
            changed.append(log_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("wiki_ingest: failed to write log.md (%s)", exc)

    # ── Corpus re-upload ──────────────────────────────────────────────────
    if changed:
        result.corpus_synced = _corpus_reupload(changed)

    return result


def _extract_channel(frontmatter: str) -> str | None:
    """Extract YouTube channel name from frontmatter author field.

    Handles YAML list form:  author:\\n  - "[[Name]]"
    and inline form:         author: "[[Name]]"
    Returns plain name with wikilink brackets and quotes stripped.
    """
    # List form: author:\n  - "[[Name]]"
    m = re.search(r'author:\s*\n\s*-\s*"?\[?\[?([^\]"\n]+)', frontmatter)
    if not m:
        # Inline form: author: "[[Name]]" or author: Name
        m = re.search(r'author:\s+"?\[?\[?([^\]"\n]+)', frontmatter)
    if not m:
        return None
    name = m.group(1).strip().rstrip('"').rstrip(']').strip()
    return name if name else None


def _enrich_youtube_frontmatter(p: Path, raw: str) -> str:
    """If the file is a YouTube clip without a channel field, add one in-place.

    Parses the source URL from frontmatter. If it's YouTube and no channel
    field exists, extracts the channel from author, injects channel: into
    the frontmatter block, and rewrites the file.

    Returns the (possibly updated) raw file content.
    """
    if not raw.startswith("---"):
        return raw
    end = raw.find("\n---", 3)
    if end == -1:
        return raw
    fm = raw[3:end]

    # Only process YouTube URLs
    if "youtube.com" not in fm and "youtu.be" not in fm:
        return raw

    # Skip if channel already has a real value (not empty or placeholder "-")
    m_ch = re.search(r'^channel:\s*"?([^"\n]*)"?', fm, re.MULTILINE)
    if m_ch and m_ch.group(1).strip() not in ("", "-"):
        return raw

    channel = _extract_channel(fm)
    if not channel:
        return raw

    # Replace placeholder or inject channel: after author: block
    if re.search(r'^channel:', fm, re.MULTILINE):
        new_fm = re.sub(
            r'^channel:.*$', f'channel: "{channel}"', fm,
            count=1, flags=re.MULTILINE,
        )
    else:
        new_fm = re.sub(
            r'(author:.*?)(\n(?!\s))',
            lambda m: m.group(1) + f"\nchannel: \"{channel}\"" + m.group(2),
            fm, count=1, flags=re.DOTALL,
        )
    updated = "---" + new_fm + "\n---" + raw[end + 4:]
    p.write_text(updated, encoding="utf-8")
    log.info("wiki_ingest: added channel=%r to %s", channel, p.name)
    return updated


def ingest_file(path: str | Path, topic: str = "") -> IngestResult:
    """Ingest a file from Sources/ into the wiki.

    For YouTube clips, extracts the channel name from the author field and
    adds it as a channel: frontmatter field (in-place update to the source
    file) before ingesting.

    Args:
        path:  Absolute path or path relative to BRAIN1_WIKI_DIR/../Sources/
        topic: Short label for log.md. Defaults to the filename stem.
    """
    p = Path(path)
    if not p.is_absolute():
        p = _wiki_dir().parent / "Sources" / path

    if not p.exists():
        r = IngestResult()
        r.status = "error"
        r.error = f"source file not found: {p}"
        return r

    raw = p.read_text(encoding="utf-8")
    raw = _enrich_youtube_frontmatter(p, raw)

    # Strip frontmatter so the LLM sees clean content + channel context
    channel = None
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm = raw[3:end]
            m = re.search(r'^channel:\s*"?([^"\n]+)"?', fm, re.MULTILINE)
            if m:
                channel = m.group(1).strip()
            raw = raw[end + 4:].lstrip()

    channel_prefix = f"[YouTube channel: {channel}]\n\n" if channel else ""
    finding = channel_prefix + raw

    label = topic or re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", p.stem)
    return ingest(finding, source_type="clip", topic=label)


__all__ = ["ingest", "ingest_file", "IngestResult"]
