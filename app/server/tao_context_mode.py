"""app/server/tao_context_mode.py — RA-1969: summary-index + on-demand expansion.

Port of `context-mode`. Walks a repo once, extracts a compact per-file synopsis
(~200 bytes vs 5-50KB raw), and serves the FULL file only when callers
explicitly `expand(path)`. Wave 1 (epic RA-1965); sibling of RA-1966
(`kill_switch`), RA-1967 (`tao_context_vcc`), RA-1968 (`tao_codebase_wiki`).

Public API:
    build_index(repo_root, ignore_globs=None) -> CodebaseIndex
    expand(index, path, max_lines=None) -> str
    stats(index) -> dict

Design points:
    * No LLM calls — pure regex symbol extraction + first-comment synopsis.
    * Deterministic given file contents (sha256 captured for invalidation).
    * Kill-switch wired: per-file LoopCounter.tick() inside build_index.
    * Default ignore globs: .git/, node_modules/, __pycache__/, .next/, dist/,
      build/, .harness/, archive/.
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .kill_switch import KillSwitchAbort, LoopCounter

log = logging.getLogger("pi-ceo.tao_context_mode")

_IGNORE_BASES = (".git", "node_modules", "__pycache__", ".next", "dist",
                 "build", ".harness", "archive", ".venv", ".pytest_cache")
DEFAULT_IGNORE_GLOBS: tuple[str, ...] = tuple(
    g for base in _IGNORE_BASES for g in (base, f"{base}/*")
)

SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".md", ".yaml", ".yml", ".toml", ".json", ".sh", ".sql",
)

_PY_SYMBOL_RE = re.compile(
    r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)", re.MULTILINE
)
_TS_SYMBOL_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)"
    r"|class\s+(\w+)"
    r"|export\s+const\s+(\w+)\s*="
)

_PY_COMMENT_PREFIX = "#"
_TS_COMMENT_PREFIXES = ("//", "/*", "*")

# Cap synopsis at 2 lines × 120 chars so even pathological huge first-line
# files stay tiny in the index. The index is only useful when compact.
_MAX_SYNOPSIS_LINES: int = 2
_MAX_SYNOPSIS_LINE_LEN: int = 120


@dataclass
class FileSummary:
    path: str
    size_bytes: int
    line_count: int
    summary: str
    symbols: list[str]
    last_modified: float
    sha256_hex: str


@dataclass
class CodebaseIndex:
    repo_root: Path
    summaries: dict[str, FileSummary] = field(default_factory=dict)
    built_at: float = 0.0
    total_bytes_indexed: int = 0
    bypassed: bool = False
    bypass_reason: str | None = None
    expansions: int = 0
    expanded_bytes: int = 0


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_ignored(rel_path: str, ignore_globs: tuple[str, ...]) -> bool:
    parts = rel_path.split("/")
    for glob in ignore_globs:
        if fnmatch.fnmatch(rel_path, glob):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, glob):
                return True
    return False


def _extract_symbols(text: str, ext: str) -> list[str]:
    """Return ordered, de-duplicated symbol names. Empty list on unknown ext."""
    if ext == ".py":
        matches = _PY_SYMBOL_RE.findall(text)
    elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        matches = _TS_SYMBOL_RE.findall(text)
    else:
        return []
    seen: list[str] = []
    for m in matches:
        names = m if isinstance(m, tuple) else (m,)
        for name in names:
            if name and name not in seen:
                seen.append(name)
    return seen


_TS_LIKE = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _strip_comment(line: str, prefixes: tuple[str, ...]) -> str:
    for p in prefixes:
        if line.startswith(p):
            return line[len(p):].strip().rstrip("*/").strip()
    return line


def _build_synopsis(text: str, ext: str) -> str:
    """First doc/comment block + first non-comment line, capped at 2 lines."""
    prefixes: tuple[str, ...] = (
        (_PY_COMMENT_PREFIX,) if ext == ".py"
        else _TS_COMMENT_PREFIXES if ext in _TS_LIKE
        else ()
    )
    lines: list[str] = []
    in_pydoc = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines:
                break
            continue
        if ext == ".py" and (line.startswith('"""') or line.startswith("'''")):
            in_pydoc = True
            doc = line.strip('"\'').strip()
            if doc:
                lines.append(doc[:_MAX_SYNOPSIS_LINE_LEN])
            if line.count('"""') == 2 or line.count("'''") == 2:
                break
            continue
        if in_pydoc:
            if '"""' in line or "'''" in line:
                break
            lines.append(line[:_MAX_SYNOPSIS_LINE_LEN])
        elif prefixes and any(line.startswith(p) for p in prefixes):
            cleaned = _strip_comment(line, prefixes)
            if cleaned:
                lines.append(cleaned[:_MAX_SYNOPSIS_LINE_LEN])
        else:
            lines.append(line[:_MAX_SYNOPSIS_LINE_LEN])
            break
        if len(lines) >= _MAX_SYNOPSIS_LINES:
            break
    return " ".join(lines[:_MAX_SYNOPSIS_LINES]) if lines else "(no synopsis)"


def _summarise_file(repo_root: Path, abs_path: Path) -> FileSummary | None:
    try:
        data = abs_path.read_bytes()
    except OSError as exc:
        log.debug("skip unreadable file %s: %s", abs_path, exc)
        return None
    try:
        text = data.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return None
    rel = str(abs_path.relative_to(repo_root)).replace(os.sep, "/")
    ext = abs_path.suffix.lower()
    summary = _build_synopsis(text, ext)
    symbols = _extract_symbols(text, ext)
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return FileSummary(
        path=rel,
        size_bytes=len(data),
        line_count=line_count,
        summary=summary,
        symbols=symbols,
        last_modified=abs_path.stat().st_mtime,
        sha256_hex=_sha256_hex(data),
    )


def build_index(
    repo_root: Path,
    *,
    ignore_globs: list[str] | None = None,
) -> CodebaseIndex:
    """Walk repo_root, summarise every source file, return CodebaseIndex.

    Pure function modulo filesystem reads; deterministic given file contents.
    Kill-switch tick per file (cost_delta_usd=0.0 — no LLM cost).
    Catches KillSwitchAbort and returns a partial index with bypassed=True.
    """
    root = Path(repo_root).resolve()
    globs = tuple(ignore_globs) if ignore_globs is not None else DEFAULT_IGNORE_GLOBS
    index = CodebaseIndex(repo_root=root, built_at=time.time())
    counter = LoopCounter()
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = str(Path(dirpath).relative_to(root)).replace(os.sep, "/")
            dirnames[:] = [
                d for d in dirnames
                if not _is_ignored(d if rel_dir == "." else f"{rel_dir}/{d}", globs)
            ]
            _index_files(root, dirpath, filenames, globs, counter, index)
    except KillSwitchAbort as abort:
        log.warning("build_index aborted by kill-switch: %s", abort.reason)
        index.bypassed = True
        index.bypass_reason = f"kill_switch:{abort.reason}"
    return index


def _index_files(root: Path, dirpath: str, filenames: list[str], globs: tuple[str, ...], counter: LoopCounter, index: CodebaseIndex) -> None:
    for name in filenames:
        if not name.endswith(SOURCE_EXTENSIONS):
            continue
        abs_p = Path(dirpath) / name
        rel = str(abs_p.relative_to(root)).replace(os.sep, "/")
        if _is_ignored(rel, globs):
            continue
        counter.tick(cost_delta_usd=0.0)
        summary = _summarise_file(root, abs_p)
        if summary is None:
            continue
        index.summaries[rel] = summary
        index.total_bytes_indexed += summary.size_bytes


def expand(
    index: CodebaseIndex,
    path: str,
    *,
    max_lines: int | None = None,
) -> str:
    """Return the full content of one file (counts as a hit).

    Verifies sha256 against the indexed value. On drift, logs a warning and
    still returns CURRENT content — caller decides whether to re-index.
    """
    summary = index.summaries.get(path)
    abs_path = (index.repo_root / path).resolve()
    try:
        data = abs_path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(f"cannot expand {path!r}: {exc}") from exc
    text = data.decode("utf-8", errors="replace")
    if summary is not None:
        current_hex = _sha256_hex(data)
        if current_hex != summary.sha256_hex:
            log.warning(
                "expand: sha256 drift for %s — index stale (indexed=%s now=%s)",
                path, summary.sha256_hex[:8], current_hex[:8],
            )
    if max_lines is not None and max_lines > 0:
        lines = text.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines]) + f"\n<truncated at {max_lines} lines>"
    index.expansions += 1
    index.expanded_bytes += len(text.encode("utf-8"))
    return text


def stats(index: CodebaseIndex) -> dict:
    files = len(index.summaries)
    total_input = max(1, index.total_bytes_indexed)
    expanded_bytes = index.expanded_bytes
    hit_rate = round(expanded_bytes / total_input, 4) if files else 0.0
    return {
        "files_indexed": files,
        "bytes_indexed": index.total_bytes_indexed,
        "expansions": index.expansions,
        "expanded_bytes": expanded_bytes,
        "hit_rate": hit_rate,
        "bypassed": index.bypassed,
        "bypass_reason": index.bypass_reason,
    }


__all__ = [
    "DEFAULT_IGNORE_GLOBS",
    "SOURCE_EXTENSIONS",
    "FileSummary",
    "CodebaseIndex",
    "build_index",
    "expand",
    "stats",
]
