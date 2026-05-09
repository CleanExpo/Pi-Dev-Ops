"""swarm/wiki_query.py — wiki-query skill implementation.

Queries the Brain-1 wiki before firing external research. Returns an answer
grounded in accumulated founder context plus confidence and go_external flag.

Public API:
    query(query_text, time_sensitive) -> QueryResult
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("swarm.wiki_query")

MAX_PAGES_TO_READ = 5
MAX_PAGE_CHARS = 1500


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class QueryResult:
    answer: str = ""
    pages_consulted: list[str] = field(default_factory=list)
    confidence: str = "low"   # "high" | "medium" | "low"
    go_external: bool = True
    stale: bool = False
    error: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _call_llm(prompt: str) -> str:
    """Gemma 4 (local, zero-cost) → Gemini 3.1 Pro fallback."""
    try:
        from . import ollama_client, config as _cfg  # noqa: PLC0415
        result = ollama_client.chat(
            model=_cfg.OLLAMA_TRIAGE_MODEL_HEAVY,
            system="You are a precise knowledge management assistant. Follow instructions exactly.",
            user_message=prompt,
            temperature=0.2,
        )
        if result:
            return result
    except Exception as _exc:  # noqa: BLE001
        log.debug("wiki_query: gemma4 unavailable (%s) — falling back to Gemini", _exc)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        key_file = Path.home() / ".margot" / "gemini-api-key.txt"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("Gemma 4 unavailable and GEMINI_API_KEY not set")

    from google import genai  # noqa: PLC0415
    text_model = os.environ.get("MARGOT_TEXT_MODEL", "gemini-3.1-pro-preview-customtools")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=text_model, contents=prompt)
    return response.text


def _identify_pages(query_text: str, index: str) -> list[str]:
    """Ask LLM which pages are most relevant to the query."""
    prompt = (
        "You are searching a personal knowledge wiki. Given the query and the "
        "wiki index below, name the ≤5 most relevant page filenames.\n\n"
        f"Wiki index:\n{index}\n\n"
        f"Query: {query_text}\n\n"
        'Reply with JSON only (no markdown fences): ["filename.md", ...]\n'
        "Rules: only name files that actually appear in the index. "
        "Never include index.md or log.md."
    )
    raw = _call_llm(prompt).strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(f) for f in result[:MAX_PAGES_TO_READ]]
    except json.JSONDecodeError:
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())[:MAX_PAGES_TO_READ]
            except json.JSONDecodeError:
                pass
    return []


def _synthesise(query_text: str, pages: dict[str, str]) -> dict:
    """Ask LLM to answer the query from the loaded page content."""
    pages_block = "\n\n".join(
        f"[{name}]\n{content}" for name, content in pages.items()
    )
    prompt = (
        "Answer the query using only the wiki pages provided. "
        "Be direct and concise — cite specific facts, dates, and numbers. "
        "If the pages don't fully answer the query, say what's missing.\n\n"
        f"Query: {query_text}\n\n"
        f"Wiki pages:\n{pages_block}\n\n"
        "Reply with JSON only (no markdown fences):\n"
        '{"answer": "...", "confidence": "high"|"medium"|"low", "stale": true|false}\n'
        "Confidence rules:\n"
        "- high: complete answer with specific facts, clearly current\n"
        "- medium: partial answer or facts that may be outdated\n"
        "- low: wiki has little or nothing relevant\n"
        "stale: true if the answer relies on dated info (>90 days for market data, "
        ">30 days for competitor/pricing data)."
    )
    raw = _call_llm(prompt).strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {"answer": raw, "confidence": "low", "stale": False}


# ── Public entry point ───────────────────────────────────────────────────────


def query(query_text: str, time_sensitive: bool = False) -> QueryResult:
    """Query the Brain-1 wiki.

    Args:
        query_text:      The question to answer.
        time_sensitive:  True for market data, competitor moves, live pricing,
                         regulatory changes — forces go_external=True regardless
                         of confidence.

    Returns:
        QueryResult. On any error, go_external=True so Margot falls through
        to external research without disruption.
    """
    result = QueryResult()
    wdir = _wiki_dir()

    if not wdir.exists():
        result.error = f"wiki dir not found: {wdir}"
        return result

    index_path = wdir / "index.md"
    if not index_path.exists():
        result.error = "index.md not found"
        return result

    index = index_path.read_text(encoding="utf-8")

    try:
        filenames = _identify_pages(query_text, index)
    except Exception as exc:  # noqa: BLE001
        result.error = f"page identification failed: {exc}"
        return result

    if not filenames:
        result.confidence = "low"
        result.go_external = True
        return result

    pages: dict[str, str] = {}
    for filename in filenames:
        p = wdir / filename
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        pages[filename] = text[:MAX_PAGE_CHARS]

    result.pages_consulted = list(pages.keys())

    if not pages:
        result.confidence = "low"
        result.go_external = True
        return result

    try:
        synthesis = _synthesise(query_text, pages)
    except Exception as exc:  # noqa: BLE001
        result.error = f"synthesis failed: {exc}"
        return result

    result.answer = synthesis.get("answer", "")
    result.confidence = synthesis.get("confidence", "low")
    result.stale = bool(synthesis.get("stale", False))

    # go_external logic
    if time_sensitive or result.stale or result.confidence == "low":
        result.go_external = True
    elif result.confidence == "medium":
        result.go_external = True   # supplement: use wiki + external
    else:
        result.go_external = False  # high confidence, fresh — wiki only

    return result


__all__ = ["query", "QueryResult"]
