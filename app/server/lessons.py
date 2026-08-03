"""
lessons.py — Institutional memory backed by .harness/lessons.jsonl, seeded on first use
from the tracked config/harness/lessons.seed.jsonl (see _ensure_seeded).

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
import logging
import os
import re
import shutil
import uuid
from collections import Counter
from datetime import timezone, datetime
from math import log
from . import config
from . import config_loader

log_ = logging.getLogger("pi-ceo.lessons")


def _ensure_seeded() -> None:
    """Install the tracked seed as the runtime store, once, and never clobber.

    `.harness/lessons.jsonl` held 49 curated lessons, added over time by deliberate
    `docs(lessons)` commits. #607 untracked `.harness/` wholesale — 609 files — and the
    lessons went with it, so a clean clone served an empty list and the smoke check
    "Lessons list is non-empty (seed data present)" failed on every run.

    Seeding by COPY rather than by reading both files is deliberate. Several call sites write
    to this store, and one of them (`_bump_occurrence`) rewrites it in place; if reads merged
    a read-only seed with the runtime file, bumping a seeded lesson would find nothing to
    rewrite and fail silently. One file at run time keeps every reader and writer correct.

    CONCURRENCY. The install must be atomic AND refuse to overwrite. An earlier version wrote
    a temp file and called `os.replace`, which is atomic but unconditional — review of #611
    demonstrated the loss: process A seeds and appends a lesson; process B, which passed its
    existence check before A finished, then replaces the store with its own pristine seed copy
    and A's append is gone for good. It also derived the temp name from the pid alone, so two
    THREADS shared one temp path and a partially-copied 17-byte store was observed.

    `os.link` fixes both. It is atomic and it fails with FileExistsError when the target
    already exists, so whoever loses the race simply does nothing and no existing store — seed
    plus appends or otherwise — is ever destroyed. The temp name carries a uuid so no two
    callers, in any thread or process, can collide on it. The temp is built from the target
    path, so it is always on the target's filesystem, which `os.link` requires.

    The runtime store stays in the untracked `.harness/` because it is appended to while the
    server runs. The seed is committed config and is never written.
    """
    path = config.LESSONS_FILE
    if os.path.exists(path):
        return
    seed = config_loader.LESSONS_SEED_JSONL
    try:
        os.stat(seed)
    except FileNotFoundError:
        # An absent seed is a legitimate configuration, not a fault: nothing to install.
        return
    except OSError as exc:
        # Not Path.is_file(): that swallows OSError into False, which would take the silent
        # branch above and make an UNREADABLE seed indistinguishable from a deliberately
        # absent one. stat() keeps the two apart — absent is legitimate, inaccessible is a
        # fault that silently disables institutional memory on every read.
        log_.error(
            "lesson seed UNREADABLE (%s): %s — the lesson store will read as EMPTY. "
            "This is a fault, not an empty-by-design store.", seed, exc,
        )
        return
    tmp = f"{path}.seed-{uuid.uuid4().hex}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(seed, tmp)
        os.link(tmp, path)
    except FileExistsError:
        # Someone else installed the store first. Correct outcome, nothing to report.
        pass
    except OSError as exc:
        # Do not raise: an empty store is degraded, a crashed caller is worse. But do not go
        # quiet either — the smoke contract requires this store to be non-empty, so a
        # persistent permissions/disk fault here disables institutional memory on every read
        # and would otherwise be indistinguishable from a deliberately absent seed.
        log_.error(
            "lesson seeding FAILED (%s -> %s): %s — the lesson store will read as EMPTY. "
            "This is a fault, not an empty-by-design store.", seed, path, exc,
        )
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# Boot-time seeding evidence (RA-7108 review finding). The read path lazily seeds —
# _read_lines() calls _ensure_seeded() — so any probe that READS the store installs the
# seed as a side effect and can never detect a dropped startup hook. This snapshot is
# written ONLY by seed_at_boot(), which only app_factory startup calls; lazy reads never
# touch it. A monitor that wants boot-state evidence asserts on the snapshot, not on a
# read.
BOOT_SEED_SNAPSHOT: dict | None = None


def seed_at_boot() -> dict:
    """Startup-only seeding entry point: seeds, then records what boot actually did.

    Returns (and stores in BOOT_SEED_SNAPSHOT) the store state as installed AT BOOT:
    whether a store already existed, and how many rows the store held immediately after
    seeding — counted by reading the file directly, not via _read_lines(), so the count
    itself cannot re-trigger seeding.
    """
    global BOOT_SEED_SNAPSHOT
    path = config.LESSONS_FILE
    existed_before = os.path.exists(path)
    _ensure_seeded()
    rows = 0
    try:
        # Count records satisfying the store's minimum content invariant, not physical
        # lines and not bare dicts: review rounds on this probe demonstrated 40 garbage
        # lines counting as 40 (018f6b7b) and 40 empty `{}` objects counting as 40
        # (c644eac0). A record counts only if it is a dict carrying a non-empty
        # `lesson` (append_lesson / seed / feedback_loop schema) or `text`
        # (append_lesson_dedup schema) string. Parsed directly, not via _read_lines(),
        # so counting cannot re-trigger seeding.
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    # JSONDecodeError subclasses ValueError; the bare ValueError also
                    # covers non-decode parse failures such as the int-digit limit.
                    continue
                if isinstance(rec, dict) and (
                    isinstance(rec.get("lesson"), str) and rec["lesson"].strip()
                    or isinstance(rec.get("text"), str) and rec["text"].strip()
                ):
                    rows += 1
    except Exception:
        # A boot-state probe must never abort boot (invalid UTF-8 raised out of the
        # line iterator at c644eac0 and would have crashed startup). Any file-level
        # read failure snapshots as 0 rows — indistinguishable from an unusable store,
        # which is exactly what an unreadable store is.
        rows = 0
    BOOT_SEED_SNAPSHOT = {
        "store_existed_before_seed": existed_before,
        "rows_after_seed": rows,
        "seeded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return BOOT_SEED_SNAPSHOT


# ── RA-7111: cross-deploy durability ─────────────────────────────────────────────────
# The container filesystem is ephemeral, so every runtime append dies with its container
# (measured live 2026-08-03→04: a runtime write raised the store to 50; the next deploy
# served exactly the 49-row seed). Every append therefore writes through to the
# lessons_durable Supabase table, and boot hydrates table rows back into the freshly
# seeded file. The single-file read path is unchanged — readers never touch Supabase.

def _write_through(entry: dict) -> None:
    """Best-effort durable copy of one appended entry. Never raises: the local append
    has already succeeded, so a failure here costs cross-deploy durability of one row,
    never availability — and it is logged, not silent."""
    try:
        from . import supabase_log  # noqa: PLC0415 — lazy, keeps import graph one-way
        supabase_log.save_lesson(entry)
    except Exception as exc:
        log_.warning("lesson write-through failed (local append intact): %s", exc)


def record_external_append(entry: dict) -> None:
    """Public write-through for the direct writers (pipeline, feedback_loop) that append
    to the store file themselves rather than via append_lesson()."""
    _write_through(entry)


def hydrate_from_durable() -> int:
    """Boot-time: append lessons_durable rows newer than the watermark into the store.

    Called once from app_factory startup, AFTER seed_at_boot(). Pure appends — the
    no-clobber install semantics are untouched. The watermark file lives next to the
    store and shares its lifecycle: on an ephemeral filesystem both die together, so a
    fresh container hydrates everything ever appended; on a persistent one, only the
    delta. Best-effort: any failure logs a warning and the boot continues seed-only.
    """
    path = config.LESSONS_FILE
    wm_path = path + ".hydrated-at"
    watermark = "1970-01-01T00:00:00Z"
    try:
        with open(wm_path, "r", encoding="utf-8") as f:
            watermark = f.read().strip() or watermark
    except OSError:
        pass
    try:
        from . import supabase_log  # noqa: PLC0415
        rows = supabase_log.fetch_lessons_since(watermark)
    except Exception as exc:
        log_.warning("lesson hydration failed (store stays seed-only this boot): %s", exc)
        return 0
    if not rows:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r["line"]) + "\n")
    newest = max(r["created_at"] for r in rows)
    tmp = wm_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(newest)
    os.replace(tmp, wm_path)
    log_.info("hydrated %d durable lesson(s); watermark now %s", len(rows), newest)
    return len(rows)


def ensure_seeded() -> None:
    """Public entry point for consumers that touch the lesson store directly.

    Several modules open `.harness/lessons.jsonl` themselves rather than going through this
    one. For readers that is merely degraded; for a WRITER it is destructive, because a
    direct append creates the file, and an existing file suppresses seeding for good — the
    49 curated lessons would then never arrive. Any such module must call this first.
    """
    _ensure_seeded()


def _read_lines() -> list[dict]:
    _ensure_seeded()
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
    _ensure_seeded()
    path = config.LESSONS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _write_through(entry)   # RA-7111: durable copy; local append already succeeded
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
    _ensure_seeded()
    path = config.LESSONS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _write_through(entry)   # RA-7111: durable copy; local append already succeeded
    return True


def _bump_occurrence(entry_id: str, entry_text: str) -> None:
    """Rewrite JSONL updating last_seen + occurrence_count for the matched entry."""
    _ensure_seeded()
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
