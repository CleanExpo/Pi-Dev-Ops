"""
lessons.py — Institutional memory backed by .harness/lessons.jsonl.

JSONL format (one JSON object per line):
  {"ts": "ISO8601", "source": "...", "category": "...", "lesson": "...", "severity": "info|warn"}

load_lessons()            — read and filter by category, newest-last
append_lesson()           — append atomically (backward-compat)
append_lesson_dedup()     — RA-1028: overlap-checked, category-typed lesson storage
check_lesson_overlap()    — RA-1028: Jaccard similarity against existing lessons
extract_lesson_from_eval()— RA-1028: heuristic lesson extraction from evaluator output
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


# ── RA-1028: Structured dedup and auto-extraction ─────────────────────────────

_VALID_CATEGORIES = frozenset(
    {"bug", "performance", "security", "architecture", "workflow", "tooling", "general"}
)


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    tokens_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def check_lesson_overlap(new_lesson: str, top_n: int = 3) -> list[dict]:
    """RA-1028: Find top-N existing lessons most similar to new_lesson.

    Uses Jaccard similarity on unigrams (intersection / union of token sets).
    Returns list of {id, text, score} sorted descending by score.
    """
    entries = _read_lines()
    if not entries:
        return []
    scored = []
    for e in entries:
        text = e.get("lesson", e.get("text", ""))
        score = _jaccard(new_lesson, text)
        if score > 0.0:
            scored.append({
                "id": e.get("id", e.get("ts", "")),
                "text": text,
                "score": round(score, 4),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def append_lesson_dedup(
    lesson_text: str,
    category: str = "general",
    repo: str = "",
    severity: str = "info",
) -> bool:
    """RA-1028: Write lesson only if no sufficiently similar entry exists.

    Checks overlap against stored lessons. If any match scores > 0.7, updates
    that entry's last_seen timestamp and occurrence_count, then returns False.
    Otherwise writes a new structured entry and returns True.

    Valid categories: bug, performance, security, architecture, workflow, tooling, general.
    """
    if category not in _VALID_CATEGORIES:
        category = "general"
    if severity not in ("info", "warn", "error"):
        severity = "info"

    matches = check_lesson_overlap(lesson_text, top_n=3)
    if matches and matches[0]["score"] > 0.7:
        # Update the matching entry in-place — rewrite the file atomically.
        _bump_occurrence(matches[0]["id"], matches[0]["text"])
        return False

    # No duplicate found — write a new structured entry.
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry_id = f"{now_ts}-{abs(hash(lesson_text)) % 10_000_000:07d}"
    entry = {
        "id": entry_id,
        "timestamp": now_ts,
        "last_seen": now_ts,
        "category": category,
        "severity": severity,
        "repo": repo[:200],
        "text": lesson_text[:300],
        "occurrence_count": 1,
    }
    path = config.LESSONS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return True


def _bump_occurrence(entry_id: str, entry_text: str) -> None:
    """Rewrite JSONL updating last_seen + occurrence_count for the matched entry."""
    path = config.LESSONS_FILE
    if not os.path.exists(path):
        return
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_lines: list[str] = []
    bumped = False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                updated_lines.append(line)
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                updated_lines.append(line)
                continue
            obj_id = obj.get("id", obj.get("ts", ""))
            obj_text = obj.get("text", obj.get("lesson", ""))
            if not bumped and (obj_id == entry_id or obj_text == entry_text):
                obj["last_seen"] = now_ts
                obj["occurrence_count"] = obj.get("occurrence_count", 1) + 1
                bumped = True
            updated_lines.append(json.dumps(obj) + "\n")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)
    os.replace(tmp, path)


def extract_lesson_from_eval(brief: str, eval_output: str, score: float) -> dict | None:
    """RA-1028: Heuristic extraction of a structured lesson from evaluator output.

    Only fires when score < 8.5. Scans sentences for negative-signal keywords,
    picks the first matching sentence, classifies it, and returns
    {text, category, severity}. Returns None if nothing actionable is found.
    No LLM call — fast and free.
    """
    if score >= 8.5:
        return None

    _PATTERNS = [
        "missing", "incorrect", "failed", "error", "should have", "not tested",
        "not implemented", "broken", "wrong", "omitted", "overlooked",
    ]

    # Tokenise eval_output into sentences (split on . ! ? or newline)
    sentences = re.split(r"(?<=[.!?])\s+|\n", eval_output)
    matched_sentence: str | None = None
    for sentence in sentences:
        low = sentence.lower()
        if any(p in low for p in _PATTERNS):
            matched_sentence = sentence.strip()
            break

    if not matched_sentence:
        return None

    # Truncate to 300 chars
    text = matched_sentence[:300]

    # Classify category from keywords
    low_text = text.lower()
    if any(k in low_text for k in ("test", "assert", "coverage", "unittest", "pytest")):
        category = "bug"
    elif any(k in low_text for k in ("performance", "slow", "latency", "timeout", "memory")):
        category = "performance"
    elif any(k in low_text for k in ("security", "auth", "permission", "injection", "xss", "csrf")):
        category = "security"
    elif any(k in low_text for k in ("import", "module", "dependency", "package", "install")):
        category = "tooling"
    else:
        category = "general"

    severity = "warn" if score < 7.0 else "info"
    return {"text": text, "category": category, "severity": severity}
