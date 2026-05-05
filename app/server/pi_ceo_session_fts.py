"""app/server/pi_ceo_session_fts.py — RA-1991 (Wave 2 / 2).

Full-text search across past Claude Code conversations using SQLite FTS5.

Port of `@kaiserlich-dev/pi-session-search`. Source corpus is
`~/.claude/projects/**/*.jsonl` — every Claude Code session writes one
jsonl per conversation with one record per turn / event.

Public API:
  * ``build_index(*, db_path=None, source_root=None) -> IndexStats``
      One-shot full rebuild. Walks every jsonl, extracts user/assistant
      text turns, writes one FTS row per turn. Deletes existing index
      before rebuilding so the path is idempotent.
  * ``rebuild_incremental(*, db_path=None, source_root=None) -> IndexStats``
      Rebuilds only conversations whose `mtime > index.mtime`. Use this
      from cron — full rebuild costs are wasteful when most files are
      unchanged.
  * ``search(query, *, limit=20, since=None, until=None, db_path=None) -> list[SearchHit]``
      BM25-ranked search. ``since``/``until`` filter by turn timestamp.
      Returns ordered list of (session_id, turn_index, role, snippet,
      score, ts_iso) hits.

Compounds with codebase-wiki (RA-1968) and context-mode (RA-1969). Every
TAO session can answer "what changed in this dir" (wiki) AND "what did
we last say about it" (this).

Kill-switch aware via the standard `LoopCounter` per RA-1966; the
indexer ticks once per file so a hard-stop file can drain a long
rebuild gracefully.

Schema:
    sessions(session_id PRIMARY KEY, source_path, mtime, indexed_at)
    turns(session_id, turn_index, role, text, ts_iso)  -- FTS5 virtual table

The FTS5 virtual table is the searchable surface; `sessions` is the
freshness-tracking table for incremental rebuilds.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

log = logging.getLogger("pi-ceo.session_fts")

DEFAULT_DB_PATH = Path.home() / ".claude" / "pi-ceo-fts.db"
DEFAULT_SOURCE_ROOT = Path.home() / ".claude" / "projects"
SCHEMA_VERSION = 1


@dataclass
class IndexStats:
    """Outcome of build_index / rebuild_incremental."""
    sessions_indexed: int = 0
    sessions_skipped: int = 0
    turns_indexed: int = 0
    elapsed_s: float = 0.0
    db_path: str = ""
    error: str | None = None


@dataclass
class SearchHit:
    """One search result row."""
    session_id: str
    turn_index: int
    role: str
    snippet: str
    score: float  # BM25 rank, lower = more relevant (FTS5 convention)
    ts_iso: str
    source_path: str = ""


@dataclass
class _Turn:
    """Internal — one extracted user/assistant turn."""
    session_id: str
    turn_index: int
    role: str
    text: str
    ts_iso: str
    source_path: str
    fields: dict = field(default_factory=dict)


# ── Schema management ────────────────────────────────────────────────────────


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — safe to run on every connect."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        INSERT OR IGNORE INTO schema_version (version) VALUES (1);

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            mtime REAL NOT NULL,
            indexed_at REAL NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS turns USING fts5(
            session_id UNINDEXED,
            turn_index UNINDEXED,
            role UNINDEXED,
            text,
            ts_iso UNINDEXED,
            tokenize = 'porter unicode61 remove_diacritics 2'
        );
        """
    )
    conn.commit()


# ── Source extraction ────────────────────────────────────────────────────────


def _extract_text(content: object) -> str:
    """Extract searchable text from a Claude Code conversation content field.

    Content can be:
      * str — direct user input
      * list[{type, text, ...}] — assistant content blocks
    Tool-use / tool-result blocks contribute their text payloads only.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif btype == "tool_use":
                # Include tool name + input text — useful for searching
                # by command/parameter intent.
                name = block.get("name") or ""
                inp = block.get("input")
                if isinstance(inp, dict):
                    inp_str = " ".join(
                        str(v) for v in inp.values() if isinstance(v, str)
                    )
                else:
                    inp_str = ""
                parts.append(f"[tool:{name}] {inp_str}".strip())
            elif btype == "tool_result":
                t = block.get("content")
                if isinstance(t, str):
                    parts.append(f"[tool_result] {t[:500]}")
                elif isinstance(t, list):
                    for sub in t:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            parts.append(f"[tool_result] {sub.get('text', '')[:500]}")
        return "\n".join(p for p in parts if p)
    return ""


def _iter_turns(jsonl_path: Path, session_id: str) -> Iterator[_Turn]:
    """Yield user/assistant turns from one conversation jsonl. Skips
    record types that don't carry conversational text."""
    turn_index = 0
    src = str(jsonl_path)
    try:
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                rtype = rec.get("type", "")
                if rtype not in ("user", "assistant"):
                    continue
                msg = rec.get("message") or {}
                role = msg.get("role") or rtype
                content = msg.get("content")
                text = _extract_text(content)
                if not text:
                    continue
                ts = rec.get("timestamp") or rec.get("ts") or ""
                if isinstance(ts, (int, float)):
                    from datetime import datetime, timezone  # noqa: PLC0415
                    ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                yield _Turn(
                    session_id=session_id, turn_index=turn_index,
                    role=role, text=text, ts_iso=str(ts),
                    source_path=src,
                )
                turn_index += 1
    except OSError as exc:
        log.warning("session_fts: cannot read %s: %s", jsonl_path, exc)


def _session_id_from_path(jsonl_path: Path) -> str:
    """Conversation jsonl filenames are UUIDs (e.g. abc123-...-def.jsonl);
    use the stem as the session id. Two conversations may share a stem
    across project dirs — prepend the project dir to disambiguate."""
    return f"{jsonl_path.parent.name}/{jsonl_path.stem}"


# ── Build / rebuild ──────────────────────────────────────────────────────────


def build_index(*, db_path: Path | None = None,
                source_root: Path | None = None,
                loop_counter=None) -> IndexStats:
    """Full rebuild from source corpus. Drops existing FTS rows first.

    Idempotent — running twice yields the same index.
    """
    db = Path(db_path) if db_path else DEFAULT_DB_PATH
    src = Path(source_root) if source_root else DEFAULT_SOURCE_ROOT
    started = time.monotonic()
    stats = IndexStats(db_path=str(db))
    if not src.exists():
        stats.error = f"source_root_missing: {src}"
        return stats
    conn = _connect(db)
    try:
        _ensure_schema(conn)
        # Wipe existing rows — full rebuild semantics
        conn.execute("DELETE FROM turns")
        conn.execute("DELETE FROM sessions")
        conn.commit()
        for jsonl_path in src.rglob("*.jsonl"):
            if loop_counter is not None:
                try:
                    loop_counter.tick()
                except Exception as exc:  # noqa: BLE001
                    log.info("session_fts: kill-switch fired: %s", exc)
                    stats.error = f"kill_switch: {exc}"
                    break
            sid = _session_id_from_path(jsonl_path)
            mtime = jsonl_path.stat().st_mtime
            turns_for_session = 0
            for turn in _iter_turns(jsonl_path, sid):
                conn.execute(
                    "INSERT INTO turns (session_id, turn_index, role, text, ts_iso) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (turn.session_id, turn.turn_index, turn.role,
                     turn.text, turn.ts_iso),
                )
                turns_for_session += 1
                stats.turns_indexed += 1
            if turns_for_session > 0:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions "
                    "(session_id, source_path, mtime, indexed_at) "
                    "VALUES (?, ?, ?, ?)",
                    (sid, str(jsonl_path), mtime, time.time()),
                )
                stats.sessions_indexed += 1
            else:
                stats.sessions_skipped += 1
        conn.commit()
    finally:
        conn.close()
    stats.elapsed_s = time.monotonic() - started
    return stats


def rebuild_incremental(*, db_path: Path | None = None,
                        source_root: Path | None = None,
                        loop_counter=None) -> IndexStats:
    """Re-index conversations whose mtime is newer than the recorded
    indexed_at, plus any new conversations. Cheap to run from cron."""
    db = Path(db_path) if db_path else DEFAULT_DB_PATH
    src = Path(source_root) if source_root else DEFAULT_SOURCE_ROOT
    started = time.monotonic()
    stats = IndexStats(db_path=str(db))
    if not src.exists():
        stats.error = f"source_root_missing: {src}"
        return stats
    conn = _connect(db)
    try:
        _ensure_schema(conn)
        # Existing index state
        row_iter = conn.execute("SELECT session_id, mtime FROM sessions")
        existing = {row["session_id"]: row["mtime"] for row in row_iter}
        for jsonl_path in src.rglob("*.jsonl"):
            if loop_counter is not None:
                try:
                    loop_counter.tick()
                except Exception as exc:  # noqa: BLE001
                    log.info("session_fts: kill-switch fired: %s", exc)
                    stats.error = f"kill_switch: {exc}"
                    break
            sid = _session_id_from_path(jsonl_path)
            mtime = jsonl_path.stat().st_mtime
            prev_mtime = existing.get(sid)
            if prev_mtime is not None and abs(mtime - prev_mtime) < 1.0:
                stats.sessions_skipped += 1
                continue
            # Re-index this session — purge old rows for it first
            conn.execute("DELETE FROM turns WHERE session_id = ?", (sid,))
            turns_for_session = 0
            for turn in _iter_turns(jsonl_path, sid):
                conn.execute(
                    "INSERT INTO turns (session_id, turn_index, role, text, ts_iso) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (turn.session_id, turn.turn_index, turn.role,
                     turn.text, turn.ts_iso),
                )
                turns_for_session += 1
                stats.turns_indexed += 1
            if turns_for_session > 0:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions "
                    "(session_id, source_path, mtime, indexed_at) "
                    "VALUES (?, ?, ?, ?)",
                    (sid, str(jsonl_path), mtime, time.time()),
                )
                stats.sessions_indexed += 1
        conn.commit()
    finally:
        conn.close()
    stats.elapsed_s = time.monotonic() - started
    return stats


# ── Search ───────────────────────────────────────────────────────────────────


def _quote_for_fts5(query: str) -> str:
    """Escape FTS5 special characters that commonly bite operators.

    Bare strings like ``RA-2002`` parse as a NEAR-style infix operator
    (FTS5 treats ``-`` as token-prefix-NOT) and raise OperationalError
    on the column lookup. Bare ``foo:bar`` similarly tries to match
    the ``foo`` column.

    Heuristic: if the query contains no double quotes AND contains a
    character that confuses the bare-string tokenizer (- : * ( )), wrap
    each whitespace-separated chunk in double quotes. Power users who
    need real FTS5 syntax (OR / NEAR / phrase) write quotes themselves.
    """
    if '"' in query:
        return query  # caller knows what they're doing
    if not any(ch in query for ch in "-:*()<>"):
        return query
    chunks = []
    for chunk in query.split():
        # Escape any embedded double quotes by doubling per FTS5 spec.
        chunk = chunk.replace('"', '""')
        chunks.append(f'"{chunk}"')
    return " ".join(chunks)


def search(query: str, *, limit: int = 20,
           since: str | None = None, until: str | None = None,
           db_path: Path | None = None) -> list[SearchHit]:
    """BM25-ranked FTS5 search.

    Args:
        query: FTS5 query string. Bare words are AND-combined; quote phrases
            with double quotes; `OR` and `NOT` operators supported.
            Hyphens, colons, and parens in bare strings are auto-quoted —
            ``RA-2002`` works as an exact-phrase search.
        limit: max results.
        since / until: ISO-8601 timestamp filters on the turn's ts_iso. Both
            optional. The ts_iso column is UNINDEXED in FTS5 but the filter
            is applied post-rank, which is fine for typical query sizes.

    Returns ordered hits (best first).
    """
    query = _quote_for_fts5(query)
    db = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not db.exists():
        return []
    conn = _connect(db)
    try:
        _ensure_schema(conn)
        sql = (
            "SELECT session_id, turn_index, role, "
            "snippet(turns, 3, '«', '»', '…', 12) AS snippet, "
            "rank, ts_iso "
            "FROM turns WHERE turns MATCH ?"
        )
        params: list[object] = [query]
        if since:
            sql += " AND ts_iso >= ?"
            params.append(since)
        if until:
            sql += " AND ts_iso <= ?"
            params.append(until)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            log.warning("session_fts: bad FTS5 query %r: %s", query, exc)
            return []
        # Source path lookup (one query per hit is fine at limit=20)
        hits: list[SearchHit] = []
        for row in rows:
            src_row = conn.execute(
                "SELECT source_path FROM sessions WHERE session_id = ?",
                (row["session_id"],),
            ).fetchone()
            hits.append(SearchHit(
                session_id=row["session_id"],
                turn_index=row["turn_index"],
                role=row["role"],
                snippet=row["snippet"] or "",
                score=row["rank"] or 0.0,
                ts_iso=row["ts_iso"] or "",
                source_path=src_row["source_path"] if src_row else "",
            ))
        return hits
    finally:
        conn.close()


__all__ = [
    "IndexStats", "SearchHit",
    "build_index", "rebuild_incremental", "search",
    "DEFAULT_DB_PATH", "DEFAULT_SOURCE_ROOT",
]
