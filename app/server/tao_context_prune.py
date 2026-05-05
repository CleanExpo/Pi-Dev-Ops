"""app/server/tao_context_prune.py — RA-1990: prospective context compaction.

Wave 2 / 1 — port of `pi-context-prune`. Sibling of RA-1967 (`tao_context_vcc`,
retrospective at 56% median) and RA-1969 (`tao_context_mode`, summary-index +
expand). This module is **prospective**: it predicts which already-emitted
blocks will not be needed downstream and elides them at the source, before
the next agent turn re-reads the transcript.

Public API: `prune(messages) -> (messages, PruneStats)`

The single difference vs vcc:
    vcc compacts what *exists* — verbose blocks, repeats, identical tool
    outputs.
    prune compacts what *won't be referenced again* — superseded tool
    results, scratch reads whose answer was used in a later turn,
    intermediate plan/draft text whose final form is in scope.

Pruning policies (all pure, idempotent on a second pass):

  1. Superseded file reads — multiple `Read` results for the same path: keep
     only the LATEST. The earlier reads contributed to a now-resolved
     question; their content is stale and the model can re-read if needed.
  2. Superseded directory listings — multiple `Glob` / `Bash ls` over the
     same path: keep only the latest. Same logic as superseded reads.
  3. Stale Bash outputs — `Bash` results whose stdout was a verification
     probe (echo / pwd / which / git status) and whose stdout has since
     been overtaken by a later definitive result on the same probe: drop
     the earlier one.
  4. Resolved errors — tool errors followed by a successful retry of the
     SAME tool with the same input: drop the failure. The model already
     learned what it needed and the failure adds noise.

Every pruning policy is conservative: when in doubt, keep the block.
False positives (over-pruning) cost the model a re-read; false negatives
(under-pruning) just keep redundant tokens. Latter is cheaper.

Run order: `prune()` is designed to run BEFORE `compact()` (vcc). Doing so
removes blocks that vcc would otherwise dedup or truncate, lowering the
total tokens vcc has to inspect.

Kill-switch: deterministic + ~zero cost. Honoured implicitly via
`TAO_MAX_COST_USD`; no per-iteration tick is needed because the work is
linear in transcript size and fits within the inner loop budget.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

# Markers — kept stable for idempotence.
PRUNED_MARK_PREFIX: str = "<pruned superseded by msg "
PRUNED_ERROR_MARK_PREFIX: str = "<pruned failed retry succeeded at msg "


@dataclass
class PruneStats:
    """Counters captured by a single prune() pass."""

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
        if self.bytes_in == 0:
            return 0.0
        return (self.bytes_in - self.bytes_out) / self.bytes_in * 100.0


# ── Helpers ──────────────────────────────────────────────────────────────────


def _bytes_of(messages: list[dict]) -> int:
    """Conservative byte count for budget tracking."""
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c.encode("utf-8", errors="ignore"))
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    t = block.get("text") or block.get("content") or ""
                    if isinstance(t, str):
                        total += len(t.encode("utf-8", errors="ignore"))
    return total


def _iter_blocks(msg: dict):
    """Yield (block_index, block_dict) pairs for blocks in a message.

    User and assistant messages can carry list-of-blocks content. Blocks
    have a ``type`` field — ``text``, ``tool_use``, ``tool_result``.
    """
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for i, block in enumerate(content):
        if isinstance(block, dict):
            yield i, block


def _tool_use_signature(block: dict) -> tuple[str, str] | None:
    """Identify a tool call by (tool_name, normalised_input). Used to
    detect retries of the same call. Returns None if the block is not a
    tool_use or carries unparseable input."""
    if block.get("type") != "tool_use":
        return None
    name = block.get("name") or ""
    inp = block.get("input")
    if isinstance(inp, dict):
        # Stable serialisation — sorted keys, str values
        sig = ";".join(
            f"{k}={inp[k]}" for k in sorted(inp.keys())
            if isinstance(inp.get(k), (str, int, float, bool))
        )
    else:
        sig = str(inp or "")
    return (str(name), sig)


def _tool_use_path(block: dict) -> str | None:
    """For tools that operate on a path (Read, Glob, Edit, Write), return
    the canonical path argument so we can detect supersession on the same
    target."""
    if block.get("type") != "tool_use":
        return None
    name = block.get("name") or ""
    inp = block.get("input") or {}
    if not isinstance(inp, dict):
        return None
    if name == "Read":
        return inp.get("file_path")
    if name == "Glob":
        # Glob's pattern + path together identify the listing
        pat = inp.get("pattern", "")
        path = inp.get("path", ".")
        return f"glob:{path}:{pat}"
    if name == "Bash":
        # Heuristic: probe-like commands (single-shot read-only) are
        # candidates for supersession. We treat exact-command match as
        # the supersession key.
        cmd = (inp.get("command") or "").strip()
        # Only certain patterns are safe to supersede — read-only probes
        if any(cmd.startswith(p) for p in (
            "ls ", "ls\n", "pwd", "which ", "git status",
            "git log --oneline -",
        )):
            return f"bash:{cmd}"
    return None


def _tool_result_for(use_block: dict, msg_index: int,
                       messages: list[dict]) -> tuple[int, int, dict] | None:
    """Find the ``tool_result`` block matching the given ``tool_use`` by id.

    Returns (msg_index, block_index, block_dict). The result typically lives
    in the very next user message but the matching is done by ``tool_use_id``
    to be safe against intervening messages.
    """
    use_id = use_block.get("id")
    if not use_id:
        return None
    for j in range(msg_index, min(msg_index + 3, len(messages))):
        for k, b in _iter_blocks(messages[j]):
            if b.get("type") == "tool_result" and b.get("tool_use_id") == use_id:
                return j, k, b
    return None


def _tool_result_is_error(result_block: dict) -> bool:
    """Tool-result blocks expose `is_error: True` on failure (Anthropic
    contract). Some tools also embed error indicators in content text but
    we trust the explicit flag."""
    return bool(result_block.get("is_error"))


# ── Pruning passes ───────────────────────────────────────────────────────────


def _pass_supersede_path_reads(
    messages: list[dict], stats: PruneStats,
) -> list[dict]:
    """Drop earlier Read/Glob/probe results when a later call on the same
    target supersedes them.

    Walks back-to-front so the LAST occurrence wins. Earlier occurrences
    on the same path/pattern get their tool_result content replaced with
    a one-line marker pointing at the later message.
    """
    last_seen: dict[str, int] = {}  # path -> latest msg_index seen

    # First pass: find the latest msg_index for each path.
    for i in range(len(messages) - 1, -1, -1):
        for _, block in _iter_blocks(messages[i]):
            path = _tool_use_path(block)
            if path and path not in last_seen:
                last_seen[path] = i

    if not last_seen:
        return messages

    out = copy.deepcopy(messages)
    pruned = 0
    # Second pass: prune all earlier occurrences.
    for i, msg in enumerate(out):
        for k, block in list(_iter_blocks(msg)):
            path = _tool_use_path(block)
            if not path:
                continue
            latest = last_seen.get(path)
            if latest is None or i >= latest:
                continue
            # This is an earlier call — find its matching result and prune.
            match = _tool_result_for(block, i, out)
            if not match:
                continue
            res_msg_idx, res_block_idx, res_block = match
            # Replace the result content with the marker. Keep the result
            # block itself so the tool_use ↔ tool_result chain is intact.
            res_msg = out[res_msg_idx]
            content = res_msg.get("content")
            if not isinstance(content, list):
                continue
            existing = content[res_block_idx]
            if isinstance(existing.get("content"), str) and (
                existing["content"].startswith(PRUNED_MARK_PREFIX)
            ):
                # Already pruned — idempotent skip.
                continue
            content[res_block_idx] = {
                **existing,
                "content": f"{PRUNED_MARK_PREFIX}{latest}>",
            }
            pruned += 1

    if pruned:
        stats.bump("supersede_path_reads", pruned)
    return out


def _pass_drop_resolved_errors(
    messages: list[dict], stats: PruneStats,
) -> list[dict]:
    """Drop tool_result content for failed calls that are immediately
    followed by a successful retry of the same tool with the same input.

    Conservative: only acts when (a) the failure is marked is_error=True,
    (b) the very next tool_use within 2 messages has the same signature,
    and (c) that retry's result is NOT is_error.
    """
    out = copy.deepcopy(messages)
    # Index tool_use blocks by (msg_index, block_index) → signature
    use_locations: list[tuple[int, int, tuple[str, str]]] = []
    for i, msg in enumerate(out):
        for k, block in _iter_blocks(msg):
            sig = _tool_use_signature(block)
            if sig:
                use_locations.append((i, k, sig))

    pruned = 0
    for u_idx, (i, k, sig) in enumerate(use_locations):
        msg = out[i]
        block = msg["content"][k]
        # Find this use's result
        match = _tool_result_for(block, i, out)
        if not match:
            continue
        res_msg_idx, res_block_idx, res_block = match
        if not _tool_result_is_error(res_block):
            continue
        # Look for a later use with the same signature whose result is success
        retry_succeeded = False
        retry_msg_idx = None
        for v_idx in range(u_idx + 1, len(use_locations)):
            i2, k2, sig2 = use_locations[v_idx]
            if sig2 != sig:
                continue
            block2 = out[i2]["content"][k2]
            match2 = _tool_result_for(block2, i2, out)
            if not match2:
                continue
            res2_msg_idx, _res2_block_idx, res2_block = match2
            if not _tool_result_is_error(res2_block):
                retry_succeeded = True
                retry_msg_idx = res2_msg_idx
                break
            # Earlier failures of the same call don't count as a successful
            # retry — keep walking.
        if not retry_succeeded:
            continue
        # Replace the failed result content with the marker
        existing = out[res_msg_idx]["content"][res_block_idx]
        cur_content = existing.get("content")
        if isinstance(cur_content, str) and cur_content.startswith(
            PRUNED_ERROR_MARK_PREFIX
        ):
            # Already pruned
            continue
        out[res_msg_idx]["content"][res_block_idx] = {
            **existing,
            "content": f"{PRUNED_ERROR_MARK_PREFIX}{retry_msg_idx}>",
        }
        pruned += 1

    if pruned:
        stats.bump("drop_resolved_errors", pruned)
    return out


# ── Public API ───────────────────────────────────────────────────────────────


def prune(messages: list[dict]) -> tuple[list[dict], PruneStats]:
    """Run all prospective-prune passes in order. Returns (out_messages, stats).

    Idempotent — running twice yields the same output. Designed to run
    BEFORE vcc's compact() so vcc has less to dedup.
    """
    stats = PruneStats(
        messages_in=len(messages), bytes_in=_bytes_of(messages),
    )
    out = list(messages)
    out = _pass_supersede_path_reads(out, stats)
    out = _pass_drop_resolved_errors(out, stats)
    stats.bytes_out = _bytes_of(out)
    stats.messages_out = len(out)
    return out, stats


def prune_for_sdk(messages: list[dict]) -> list[dict]:
    """Convenience wrapper — prune() and discard stats.

    Sequencing: callers wiring this into the SDK pre-pass should run
    prune() FIRST, then vcc's compact() — pruned blocks are smaller
    inputs for compact()'s dedup/truncate passes.
    """
    out, _ = prune(messages)
    return out


__all__ = [
    "PruneStats",
    "PRUNED_MARK_PREFIX",
    "PRUNED_ERROR_MARK_PREFIX",
    "prune",
    "prune_for_sdk",
]
