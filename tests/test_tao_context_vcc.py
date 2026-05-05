"""tests/test_tao_context_vcc.py — RA-1967 compactor unit tests.

Cover each technique in isolation, the stats dataclass, idempotence, the
no-op short-transcript case, and the best-effort token budget hint.
All tests run pure in-process — no SDK, no I/O.
"""
from __future__ import annotations

from app.server.tao_context_vcc import (
    DEDUP_MARK_PREFIX,
    ELISION_MARK_PREFIX,
    HEAD_TAIL_LINES,
    MAX_BYTES_PER_BLOCK,
    REPEAT_MARK_PREFIX,
    CompactionStats,
    compact,
    compact_for_sdk,
)


# ── Technique (a) — tool-output dedup ─────────────────────────────────────────

def test_tool_dedup_replaces_repeats_with_back_reference():
    """Two identical `tool` turns → second becomes `<truncated: same as msg N>`."""
    big = "PAYLOAD\n" * 100
    msgs = [
        {"role": "user", "content": "ls"},
        {"role": "tool", "content": big},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "ls again"},
        {"role": "tool", "content": big},
    ]
    out, stats = compact(msgs)
    assert stats.techniques_applied.get("tool_dedup", 0) == 1
    assert DEDUP_MARK_PREFIX in out[4]["content"]
    # First tool turn is preserved verbatim.
    assert out[1]["content"] == big


def test_tool_dedup_preserves_non_tool_repeats():
    """User/assistant duplicates are NOT touched by dedup pass on its own."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "hello"},
    ]
    out, stats = compact(msgs)
    # The two non-adjacent user "hello"s are not deduped (no tool role).
    assert stats.techniques_applied.get("tool_dedup", 0) == 0


# ── Technique (b) — verbose-block truncation ──────────────────────────────────

def test_verbose_block_truncated_with_elision_marker():
    """A >50 KB tool output is clipped to head + tail with an elision marker."""
    huge = "x" * (MAX_BYTES_PER_BLOCK + 1000)
    msgs = [
        {"role": "user", "content": "cat huge.log"},
        {"role": "tool", "content": huge},
    ]
    out, stats = compact(msgs)
    assert stats.techniques_applied.get("verbose_truncate", 0) == 1
    assert ELISION_MARK_PREFIX in out[1]["content"]
    assert len(out[1]["content"]) < len(huge)


def test_verbose_truncation_uses_head_and_tail():
    """A long line-based block keeps head + tail rather than head only."""
    body = "\n".join(f"line-{i}" for i in range(5000))
    msgs = [{"role": "tool", "content": body}]
    out, _ = compact(msgs)
    text = out[0]["content"]
    assert "line-0" in text and "line-4999" in text
    # Lines well into the middle should be elided.
    assert "line-2500" not in text


# ── Technique (c) — repeat-pattern collapse ───────────────────────────────────

def test_repeat_collapse_consecutive_identical_messages():
    """Five identical adjacent assistant messages → one with `<repeated 5 times>`."""
    msgs = [
        {"role": "user", "content": "go"},
        *[{"role": "assistant", "content": "ping"} for _ in range(5)],
        {"role": "user", "content": "done"},
    ]
    out, stats = compact(msgs)
    assert stats.techniques_applied.get("repeat_collapse", 0) == 4  # 5 → 1 = 4 dropped
    assert any(REPEAT_MARK_PREFIX in m["content"] for m in out)
    assert len(out) == 3  # user, collapsed-assistant, user


# ── Technique (d) — whitespace + log-noise normalisation ──────────────────────

def test_whitespace_normalisation_strips_trailing_and_dedups_blanks():
    """Trailing spaces, multiple blank lines, and CRLF all normalise."""
    raw = "hello   \r\nworld\n\n\n\nbye  "
    msgs = [{"role": "user", "content": raw}]
    out, stats = compact(msgs)
    text = out[0]["content"]
    assert "hello" in text and "world" in text and "bye" in text
    assert "\r" not in text
    assert "   \n" not in text
    assert "\n\n\n" not in text
    assert stats.techniques_applied.get("whitespace_normalise", 0) == 1


# ── Stats dataclass ───────────────────────────────────────────────────────────

def test_stats_populated_correctly():
    """Bytes/messages counters reflect input + output sizes."""
    big = "x" * (MAX_BYTES_PER_BLOCK + 1000)
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": big},
    ]
    out, stats = compact(msgs)
    assert isinstance(stats, CompactionStats)
    assert stats.messages_in == 2
    assert stats.messages_out == len(out)
    assert stats.bytes_in > stats.bytes_out
    assert stats.pct_reduction > 0


# ── Idempotence ───────────────────────────────────────────────────────────────

def test_compaction_idempotent_on_second_pass():
    """compact(compact(x)) ≡ compact(x). A second call should not shrink further."""
    huge = "y" * (MAX_BYTES_PER_BLOCK + 500)
    msgs = [
        {"role": "user", "content": "ls"},
        {"role": "tool", "content": huge},
        {"role": "tool", "content": huge},
    ]
    once, stats_once = compact(msgs)
    twice, stats_twice = compact(once)
    assert stats_twice.bytes_out == stats_once.bytes_out
    assert twice == once


# ── No-op case ────────────────────────────────────────────────────────────────

def test_short_transcript_returns_unchanged():
    """A short, clean transcript triggers no compaction and round-trips intact."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out, stats = compact(msgs)
    assert out == msgs
    assert sum(stats.techniques_applied.values()) == 0


# ── Token budget hint ─────────────────────────────────────────────────────────

def test_target_token_budget_short_circuits_when_already_under():
    """Already-under-budget input returns immediately with zero techniques applied."""
    msgs = [{"role": "user", "content": "hi"}]
    _, stats = compact(msgs, target_token_budget=10_000)
    assert sum(stats.techniques_applied.values()) == 0


def test_target_token_budget_drives_compaction_to_completion():
    """Large input + tight budget still produces a smaller transcript."""
    huge = "z" * (MAX_BYTES_PER_BLOCK + 4000)
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "tool", "content": huge},
        {"role": "tool", "content": huge},
    ]
    _, stats = compact(msgs, target_token_budget=1_000)
    assert stats.bytes_out < stats.bytes_in


# ── List-of-blocks message shape ──────────────────────────────────────────────

def test_assistant_list_of_blocks_shape_is_handled():
    """Assistant messages with list-of-blocks content normalise without crashing."""
    msgs = [
        {"role": "user", "content": "    "},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "trailing   "},
                {"type": "text", "text": "ws    "},
            ],
        },
    ]
    out, _ = compact(msgs)
    assert isinstance(out[1]["content"], list)
    assert "    " not in out[1]["content"][0]["text"]


# ── Wrapper helper ────────────────────────────────────────────────────────────

def test_compact_for_sdk_returns_messages_only():
    """Wrapper drops stats and returns just the compacted messages list."""
    msgs = [{"role": "user", "content": "x"}]
    out = compact_for_sdk(msgs)
    assert isinstance(out, list)
    assert out == msgs
