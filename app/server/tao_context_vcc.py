"""app/server/tao_context_vcc.py — RA-1967: deterministic conversation compactor.

Port of `@sting8k/pi-vcc`. Algorithmic, transcript-preserving compaction that
runs in the hot path with NO LLM calls. Wave 1 (epic RA-1965); sibling of
RA-1966 (`kill_switch`) and RA-1970 (tao-judge / tao-loop).

Public API: `compact(messages, target_token_budget=None) -> (messages, stats)`
plus `compact_for_sdk(messages)` convenience wrapper.

Techniques (all pure, idempotent on second pass):
    a. tool-output dedup       — repeat tool turns -> `<truncated: same as msg N>`.
    b. verbose-block truncate  — >2000 lines or >50KB clipped to head+tail.
    c. repeat-pattern collapse — adjacent identical msgs -> `<repeated K times>`.
    d. whitespace normalise    — trailing-ws strip, blank-line dedup, CRLF -> LF.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

# ── Tunables ──────────────────────────────────────────────────────────────────
MAX_LINES_PER_BLOCK: int = 2000
MAX_BYTES_PER_BLOCK: int = 50_000
HEAD_TAIL_LINES: int = 40           # lines kept on each side of an elision
TOKEN_BYTES_RATIO: int = 4          # rough cl100k_base bytes-per-token proxy

# Markers (idempotence relies on these being stable + recognisable).
ELISION_MARK_PREFIX: str = "<elided "
DEDUP_MARK_PREFIX: str = "<truncated: same as msg "
REPEAT_MARK_PREFIX: str = "<repeated "


@dataclass
class CompactionStats:
    """Counters captured by a single compact() pass."""

    bytes_in: int = 0
    bytes_out: int = 0
    messages_in: int = 0
    messages_out: int = 0
    techniques_applied: dict[str, int] = field(default_factory=dict)

    def bump(self, technique: str, n: int = 1) -> None:
        self.techniques_applied[technique] = (
            self.techniques_applied.get(technique, 0) + n
        )

    @property
    def pct_reduction(self) -> float:
        if self.bytes_in <= 0:
            return 0.0
        return round(100.0 * (1.0 - self.bytes_out / self.bytes_in), 2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _content_to_text(content: Any) -> str:
    """Flatten the SDK message content into a single string.

    Handles both `content: str` and `content: [block, ...]` (list of dicts
    with `text` or `content` keys, falling back to `str(block)`).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _set_content_text(msg: dict, text: str) -> None:
    """Write `text` into `msg["content"]`, preserving str/list shape.

    List-of-blocks messages collapse to a single text block — downstream
    consumers only read text from compacted output.
    """
    if isinstance(msg.get("content"), list):
        msg["content"] = [{"type": "text", "text": text}]
    else:
        msg["content"] = text


def _normalise_whitespace(text: str) -> tuple[str, bool]:
    """Strip trailing ws on each line, dedup blank-line runs, normalise CRLF.

    Returns (normalised_text, changed?).
    """
    crlf_normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in crlf_normalised.split("\n")]
    out: list[str] = []
    prev_blank = False
    for line in lines:
        if line == "":
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        out.append(line)
    new_text = "\n".join(out)
    return new_text, new_text != text


def _truncate_if_verbose(text: str) -> tuple[str, bool]:
    """Technique (b) — head+tail truncation past line/byte ceilings. Idempotent."""
    if ELISION_MARK_PREFIX in text:
        return text, False
    line_count = text.count("\n") + 1
    byte_len = len(text.encode("utf-8"))
    if line_count <= MAX_LINES_PER_BLOCK and byte_len <= MAX_BYTES_PER_BLOCK:
        return text, False
    # Two regimes: many-line -> keep N head/tail LINES; few-line oversize ->
    # keep head/tail BYTE slices. Both emit a marker prefixed with
    # ELISION_MARK_PREFIX so the next pass becomes a no-op.
    if line_count > 2 * HEAD_TAIL_LINES + 1:
        lines = text.split("\n")
        head = lines[:HEAD_TAIL_LINES]
        tail = lines[-HEAD_TAIL_LINES:]
        elided_lines = len(lines) - len(head) - len(tail)
        kept_bytes = len("\n".join(head + tail).encode("utf-8"))
        elided_bytes = max(0, byte_len - kept_bytes)
        marker = (
            f"{ELISION_MARK_PREFIX}{elided_lines} lines, "
            f"{elided_bytes} bytes>"
        )
        return "\n".join(head + [marker] + tail), True

    # Few-line, byte-heavy regime — keep head + tail byte slices.
    head_bytes = text[:HEAD_TAIL_LINES * 80]
    tail_bytes = text[-HEAD_TAIL_LINES * 80:]
    elided_bytes = max(0, byte_len - len(head_bytes.encode("utf-8")) - len(tail_bytes.encode("utf-8")))
    marker = f"{ELISION_MARK_PREFIX}0 lines, {elided_bytes} bytes>"
    return f"{head_bytes}\n{marker}\n{tail_bytes}", True


def _msg_key(msg: dict) -> tuple[str, str]:
    """Identity tuple for dedup / repeat detection — role + flattened text."""
    return (str(msg.get("role", "")), _content_to_text(msg.get("content", "")))


def _bytes_of(messages: list[dict]) -> int:
    return sum(len(_content_to_text(m.get("content", "")).encode("utf-8")) for m in messages)


# ── Core passes ───────────────────────────────────────────────────────────────

def _pass_collapse_repeats(messages: list[dict], stats: CompactionStats) -> list[dict]:
    """Technique (c) — runs of identical (role, content) collapse to one msg."""
    out: list[dict] = []
    i = 0
    while i < len(messages):
        run_end = i + 1
        key = _msg_key(messages[i])
        while run_end < len(messages) and _msg_key(messages[run_end]) == key:
            run_end += 1
        run_len = run_end - i
        if run_len >= 2:
            head = copy.deepcopy(messages[i])
            text = _content_to_text(head.get("content", ""))
            text = f"{text}\n{REPEAT_MARK_PREFIX}{run_len} times>"
            _set_content_text(head, text)
            out.append(head)
            stats.bump("repeat_collapse", run_len - 1)
        else:
            out.append(messages[i])
        i = run_end
    return out


def _pass_truncate_verbose(messages: list[dict], stats: CompactionStats) -> list[dict]:
    """Technique (b) — head/tail truncation of >2000-line / >50KB blocks."""
    out: list[dict] = []
    for msg in messages:
        text = _content_to_text(msg.get("content", ""))
        new_text, changed = _truncate_if_verbose(text)
        if changed:
            new_msg = copy.deepcopy(msg)
            _set_content_text(new_msg, new_text)
            out.append(new_msg)
            stats.bump("verbose_truncate")
        else:
            out.append(msg)
    return out


def _pass_dedup_tools(messages: list[dict], stats: CompactionStats) -> list[dict]:
    """Technique (a) — duplicate tool outputs replaced by a back-reference."""
    out: list[dict] = []
    first_seen: dict[tuple[str, str], int] = {}
    for idx, msg in enumerate(messages):
        role = str(msg.get("role", ""))
        if role != "tool":
            out.append(msg)
            continue
        key = _msg_key(msg)
        if key in first_seen:
            ref_idx = first_seen[key]
            new_msg = copy.deepcopy(msg)
            _set_content_text(new_msg, f"{DEDUP_MARK_PREFIX}{ref_idx}>")
            out.append(new_msg)
            stats.bump("tool_dedup")
        else:
            first_seen[key] = idx
            out.append(msg)
    return out


def _pass_normalise_ws(messages: list[dict], stats: CompactionStats) -> list[dict]:
    """Technique (d) — whitespace + log-noise normalisation."""
    out: list[dict] = []
    for msg in messages:
        text = _content_to_text(msg.get("content", ""))
        new_text, changed = _normalise_whitespace(text)
        if changed:
            new_msg = copy.deepcopy(msg)
            _set_content_text(new_msg, new_text)
            out.append(new_msg)
            stats.bump("whitespace_normalise")
        else:
            out.append(msg)
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def compact(
    messages: list[dict],
    target_token_budget: int | None = None,
) -> tuple[list[dict], CompactionStats]:
    """Compact a transcript with deterministic, LLM-free techniques.

    Order of passes (each may be skipped early once budget is met):
      1. whitespace normalise       — cheap, always run
      2. repeat-pattern collapse    — preserves first occurrence
      3. tool-output dedup          — references earlier identical tool turn
      4. verbose-block truncation   — head + tail with elision marker

    `target_token_budget` is a best-effort hint. Each pass checks the running
    byte estimate (`bytes / TOKEN_BYTES_RATIO`) and stops early once under
    budget so we never compact more than necessary.
    """
    stats = CompactionStats(messages_in=len(messages), bytes_in=_bytes_of(messages))

    def _under_budget(current: list[dict]) -> bool:
        if target_token_budget is None:
            return False
        return (_bytes_of(current) / TOKEN_BYTES_RATIO) <= target_token_budget

    out = list(messages)
    if _under_budget(out):
        stats.bytes_out = _bytes_of(out)
        stats.messages_out = len(out)
        return out, stats
    out = _pass_normalise_ws(out, stats)
    if not _under_budget(out):
        out = _pass_collapse_repeats(out, stats)
    if not _under_budget(out):
        out = _pass_dedup_tools(out, stats)
    if not _under_budget(out):
        out = _pass_truncate_verbose(out, stats)

    stats.bytes_out = _bytes_of(out)
    stats.messages_out = len(out)
    return out, stats


def compact_for_sdk(messages: list[dict]) -> list[dict]:
    """Convenience wrapper — compact() and discard stats.

    TODO(RA-1967): wiring as a pre-pass on `_run_claude_via_sdk` is deferred
    because that function takes a `prompt: str` rather than a messages list.
    Pre-pass requires either an SDK-call-surface refactor or a parse/render
    round-trip; both are wider than this Wave 1 primitive. RA-1970 (tao-loop)
    will settle the canonical TAO message representation.
    """
    out, _ = compact(messages)
    return out


__all__ = [
    "CompactionStats",
    "MAX_LINES_PER_BLOCK",
    "MAX_BYTES_PER_BLOCK",
    "HEAD_TAIL_LINES",
    "TOKEN_BYTES_RATIO",
    "compact",
    "compact_for_sdk",
]
