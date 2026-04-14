"""
lessons.py — Institutional memory backed by .harness/lessons.jsonl.

JSONL format (one JSON object per line):
  {"ts": "ISO8601", "source": "...", "category": "...", "lesson": "...", "severity": "info|warn"}

load_lessons()            — read and filter by category, newest-last
append_lesson()           — append atomically
search_lessons_keyword()  — RA-927: TF-IDF-style keyword search, stdlib-only (runs on Railway)

Semantic search (RA-927 local use) lives in .harness/lessons_search.py (ChromaDB, local-only).
"""
import json
import os
import re
from collections import Counter
from datetime import timezone, datetime
from math import log
from . import config


def _read_lines() -> list[dict]:
    path = config.LESSONS_FILE
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def load_lessons(category: str | None = None, limit: int = 50) -> list[dict]:
    """Return lessons, optionally filtered by category, newest-last, up to limit."""
    entries = _read_lines()
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return entries[-limit:]


def search_lessons_keyword(query: str, n: int = 5, min_score: float = 0.1) -> list[dict]:
    """RA-927: BM25-style keyword search over lessons.jsonl — stdlib-only, zero new deps.

    Tokenises the query and each lesson, scores by term frequency × inverse document
    frequency approximation, returns top-n results above min_score.

    No semantic understanding — use .harness/lessons_search.py (ChromaDB) locally
    for the full semantic + HyDE experience.
    """
    entries = _read_lines()
    if not entries:
        return []

    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    query_tokens = set(_tokens(query))
    if not query_tokens:
        return entries[-n:]

    # IDF: log(N / df) for each query token
    N = len(entries)
    df: Counter = Counter()
    for e in entries:
        doc_tokens = set(_tokens(e.get("lesson", "")))
        for t in query_tokens:
            if t in doc_tokens:
                df[t] += 1

    idf = {t: log((N + 1) / (df.get(t, 0) + 1)) for t in query_tokens}

    scored = []
    for e in entries:
        lesson_text = e.get("lesson", "")
        tokens = _tokens(lesson_text)
        token_count = len(tokens) or 1
        tf = Counter(tokens)
        score = sum((tf[t] / token_count) * idf[t] for t in query_tokens)
        # Boost warn severity slightly — those lessons are more critical
        if e.get("severity") == "warn":
            score *= 1.2
        if score >= min_score:
            scored.append({**e, "_score": round(score, 4)})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    # Strip internal score key from returned dicts
    return [{k: v for k, v in r.items() if k != "_score"} for r in scored[:n]]


def append_lesson(source: str, category: str, lesson: str, severity: str = "info") -> dict:
    """Append a new lesson to the JSONL file. Returns the saved entry."""
    if severity not in ("info", "warn"):
        severity = "info"
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source[:100],
        "category": category[:50],
        "lesson": lesson[:500],
        "severity": severity,
    }
    path = config.LESSONS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
