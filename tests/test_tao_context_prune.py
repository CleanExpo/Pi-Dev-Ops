"""tests/test_tao_context_prune.py — RA-1990 regression coverage.

Pins the prune() contract:
  * Superseded Read/Glob/probe results get replaced with a marker pointing
    at the latest call on the same target.
  * Resolved tool errors (failure → same-input retry that succeeds) get
    their failure content replaced with a marker pointing at the retry.
  * Idempotent on a second pass.
  * No-op when the transcript has no candidates.
  * Conservative: latest copy is preserved (for path supersession), and
    a failure with no successful retry stays untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.tao_context_prune import (  # noqa: E402
    PRUNED_ERROR_MARK_PREFIX,
    PRUNED_MARK_PREFIX,
    PruneStats,
    prune,
    prune_for_sdk,
)


def _tool_use(uid: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": uid, "name": name, "input": inp}


def _tool_result(uid: str, content: str, *, is_error: bool = False) -> dict:
    return {
        "type": "tool_result", "tool_use_id": uid,
        "content": content, "is_error": is_error,
    }


def _msg(role: str, blocks: list) -> dict:
    return {"role": role, "content": blocks}


# ── Path supersession (Read) ─────────────────────────────────────────────────


def test_repeated_read_supersedes_earlier(tmp_path):
    """Two Reads of the same file — earlier one's result replaced."""
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/foo.py")]),
        _msg("user", [_tool_result("a1", "first read content " * 50)]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/foo.py")]),
        _msg("user", [_tool_result("a2", "latest content")]),
    ]
    out, stats = prune(messages)
    # First read result should be pruned to a marker
    first_result = out[1]["content"][0]
    assert first_result["content"].startswith(PRUNED_MARK_PREFIX)
    # Latest read result must be UNTOUCHED
    last_result = out[3]["content"][0]
    assert last_result["content"] == "latest content"
    assert stats.techniques_applied.get("supersede_path_reads") == 1
    # Stats sanity
    assert stats.bytes_out < stats.bytes_in


def test_three_reads_only_latest_kept():
    """3 Reads of same file → first 2 pruned, latest preserved."""
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a1", "v1 " * 100)]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a2", "v2 " * 100)]),
        _msg("assistant", [_tool_use("a3", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a3", "v3 final")]),
    ]
    out, stats = prune(messages)
    assert out[1]["content"][0]["content"].startswith(PRUNED_MARK_PREFIX)
    assert out[3]["content"][0]["content"].startswith(PRUNED_MARK_PREFIX)
    assert out[5]["content"][0]["content"] == "v3 final"
    assert stats.techniques_applied.get("supersede_path_reads") == 2


def test_reads_of_different_files_untouched():
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/foo")]),
        _msg("user", [_tool_result("a1", "foo content")]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/bar")]),
        _msg("user", [_tool_result("a2", "bar content")]),
    ]
    out, stats = prune(messages)
    # Neither pruned
    assert out[1]["content"][0]["content"] == "foo content"
    assert out[3]["content"][0]["content"] == "bar content"
    assert "supersede_path_reads" not in stats.techniques_applied


# ── Path supersession (Glob) ─────────────────────────────────────────────────


def test_repeated_glob_supersedes_earlier():
    messages = [
        _msg("assistant", [_tool_use("g1", "Glob",
                                       pattern="*.py", path="/x")]),
        _msg("user", [_tool_result("g1", "[older listing] " * 30)]),
        _msg("assistant", [_tool_use("g2", "Glob",
                                       pattern="*.py", path="/x")]),
        _msg("user", [_tool_result("g2", "newest listing")]),
    ]
    out, _ = prune(messages)
    assert out[1]["content"][0]["content"].startswith(PRUNED_MARK_PREFIX)
    assert out[3]["content"][0]["content"] == "newest listing"


def test_glob_different_patterns_untouched():
    messages = [
        _msg("assistant", [_tool_use("g1", "Glob", pattern="*.py", path="/")]),
        _msg("user", [_tool_result("g1", "py listing")]),
        _msg("assistant", [_tool_use("g2", "Glob", pattern="*.ts", path="/")]),
        _msg("user", [_tool_result("g2", "ts listing")]),
    ]
    out, _ = prune(messages)
    assert out[1]["content"][0]["content"] == "py listing"
    assert out[3]["content"][0]["content"] == "ts listing"


# ── Bash probe supersession ──────────────────────────────────────────────────


def test_repeated_git_status_supersedes_earlier():
    messages = [
        _msg("assistant", [_tool_use("b1", "Bash", command="git status")]),
        _msg("user", [_tool_result("b1", "older status")]),
        _msg("assistant", [_tool_use("b2", "Bash", command="git status")]),
        _msg("user", [_tool_result("b2", "newer status")]),
    ]
    out, _ = prune(messages)
    assert out[1]["content"][0]["content"].startswith(PRUNED_MARK_PREFIX)
    assert out[3]["content"][0]["content"] == "newer status"


def test_non_probe_bash_untouched():
    """Non-read-only Bash commands MUST NOT be superseded — they have
    side effects and the result is canonical history."""
    messages = [
        _msg("assistant", [_tool_use("b1", "Bash", command="rm /tmp/x")]),
        _msg("user", [_tool_result("b1", "removed")]),
        _msg("assistant", [_tool_use("b2", "Bash", command="rm /tmp/x")]),
        _msg("user", [_tool_result("b2", "missing")]),
    ]
    out, stats = prune(messages)
    # Both kept
    assert out[1]["content"][0]["content"] == "removed"
    assert out[3]["content"][0]["content"] == "missing"
    assert "supersede_path_reads" not in stats.techniques_applied


# ── Resolved errors ──────────────────────────────────────────────────────────


def test_failed_call_followed_by_successful_retry_pruned():
    messages = [
        _msg("assistant", [_tool_use("e1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("e1", "Permission denied", is_error=True)]),
        _msg("assistant", [_tool_use("e2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("e2", "actual content")]),
    ]
    out, stats = prune(messages)
    # The Read was superseded too (same path) — but the test exercises
    # both rules. Either marker is acceptable here; what matters is the
    # failure content is gone and the success is preserved.
    first = out[1]["content"][0]["content"]
    assert (first.startswith(PRUNED_MARK_PREFIX)
            or first.startswith(PRUNED_ERROR_MARK_PREFIX))
    assert out[3]["content"][0]["content"] == "actual content"


def test_failed_call_with_no_retry_untouched():
    messages = [
        _msg("assistant", [_tool_use("e1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("e1", "Permission denied", is_error=True)]),
    ]
    out, stats = prune(messages)
    assert out[1]["content"][0]["content"] == "Permission denied"
    assert out[1]["content"][0]["is_error"] is True


def test_failed_call_followed_by_another_failure_untouched():
    """Two failures, no success — keep both."""
    messages = [
        _msg("assistant", [_tool_use("e1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("e1", "err1", is_error=True)]),
        _msg("assistant", [_tool_use("e2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("e2", "err2", is_error=True)]),
    ]
    out, _ = prune(messages)
    # The path-supersession rule still applies — earlier read superseded.
    # But neither failure is "resolved" (no success), so the
    # drop_resolved_errors marker MUST NOT appear.
    for msg in out:
        for b in msg.get("content", []):
            if isinstance(b, dict):
                c = b.get("content")
                if isinstance(c, str):
                    assert not c.startswith(PRUNED_ERROR_MARK_PREFIX)


# ── Idempotence ──────────────────────────────────────────────────────────────


def test_prune_is_idempotent():
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a1", "old " * 50)]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a2", "new")]),
    ]
    once, _ = prune(messages)
    twice, stats2 = prune(once)
    # Outputs identical
    assert once == twice
    # Second pass should report 0 new prunes
    assert stats2.techniques_applied.get("supersede_path_reads", 0) == 0


# ── No-op cases ──────────────────────────────────────────────────────────────


def test_empty_input():
    out, stats = prune([])
    assert out == []
    assert stats.bytes_in == 0
    assert stats.bytes_out == 0


def test_text_only_messages_untouched():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out, stats = prune(messages)
    assert out == messages
    assert stats.techniques_applied == {}


def test_tool_use_without_result_untouched():
    """Orphan tool_use with no matching tool_result — pass-through."""
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/x")]),
        # No matching tool_result — model crashed mid-turn
        _msg("assistant", [_tool_use("a2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a2", "content")]),
    ]
    out, _ = prune(messages)
    # Latest Read still there
    assert out[2]["content"][0]["content"] == "content"


# ── Pct-reduction sanity ─────────────────────────────────────────────────────


def test_pct_reduction_positive_when_pruning_happens():
    big = "x" * 5000
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a1", big)]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a2", "tiny")]),
    ]
    _, stats = prune(messages)
    assert stats.pct_reduction > 50.0


def test_pct_reduction_zero_on_empty():
    stats = PruneStats(bytes_in=0, bytes_out=0)
    assert stats.pct_reduction == 0.0


# ── prune_for_sdk wrapper ────────────────────────────────────────────────────


def test_prune_for_sdk_returns_messages_only():
    messages = [
        _msg("assistant", [_tool_use("a1", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a1", "old")]),
        _msg("assistant", [_tool_use("a2", "Read", file_path="/x")]),
        _msg("user", [_tool_result("a2", "new")]),
    ]
    out = prune_for_sdk(messages)
    assert isinstance(out, list)
    # Same content as prune()'s first return value
    out_full, _ = prune(messages)
    assert out == out_full
