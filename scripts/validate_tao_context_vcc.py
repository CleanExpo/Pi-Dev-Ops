#!/usr/bin/env python3
"""scripts/validate_tao_context_vcc.py — RA-1967 manual-verification harness.

Runs `compact()` on saved transcripts and reports per-session pct_reduction
plus an aggregate (median + mean + overall). Exits 0 when median ≥ threshold
(default 30%, per 2026-05-05 board memo), else 1.

Two corpora are accepted, auto-detected by record shape:

  1. Conversation jsonl from `~/.claude/projects/<encoded-cwd>/<id>.jsonl`.
     Each line is a record carrying `message: {role, content}`. This is the
     primary corpus — full Claude Code transcripts with text + tool blocks.
  2. SDK metrics jsonl from `.harness/agent-sdk-metrics/`. Records carry
     `phase` / `session_id` / `output_len` only — no message content. The
     harness skips these with a stderr warning so the GH Action / docs
     pointing at the metrics dir do not crash.

Token counting prefers `tiktoken` (cl100k_base). Falls back to bytes/4.

Usage:
    python3 scripts/validate_tao_context_vcc.py --root ~/.claude/projects -n 10
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

# Make the app importable when run as a top-level script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.server.tao_context_vcc import compact  # noqa: E402


def _resolve_token_counter():
    """Return (callable text -> int, label). Prefers tiktoken; falls back to bytes/4."""
    try:
        import tiktoken  # type: ignore  # noqa: PLC0415

        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda t: len(enc.encode(t))), "tiktoken-cl100k_base"
    except Exception:
        sys.stderr.write("[validate] tiktoken unavailable — bytes/4 proxy\n")
        return (lambda t: max(1, len(t.encode("utf-8")) // 4)), "bytes-div-4"


def _flatten(messages: list[dict]) -> str:
    """Symmetric flatten — counts FULL JSON wire form for input and output.

    Anthropic API charges tokens against the JSON-serialised request, so the
    fair measurement is the wire-form size, not block.text alone.
    """
    parts: list[str] = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    if isinstance(block.get("text"), str):
                        parts.append(block["text"])
                    else:
                        parts.append(json.dumps(block, ensure_ascii=False))
                else:
                    parts.append(str(block))
        else:
            parts.append(str(c))
    return "\n".join(parts)


def _extract_messages(jsonl_path: Path) -> tuple[list[dict], str]:
    """Pull message records out of a jsonl. Returns (messages, shape_label).

    shape_label is one of:
      - "conversation"  — records have `message: {role, content}`
      - "sdk-metrics"   — records have `phase`/`session_id`/`output_len`
      - "unknown"       — neither shape recognised
    """
    out: list[dict] = []
    saw_metrics = False
    saw_conversation = False
    try:
        text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], "unknown"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        msg = rec.get("message")
        if isinstance(msg, dict) and msg.get("role") in {"user", "assistant"}:
            saw_conversation = True
            out.append({"role": msg["role"], "content": msg.get("content", "")})
            continue
        if isinstance(rec.get("role"), str) and "content" in rec:
            saw_conversation = True
            out.append({"role": rec["role"], "content": rec.get("content", "")})
            continue
        if "phase" in rec or "output_len" in rec or "session_id" in rec:
            saw_metrics = True
    if out:
        return out, "conversation"
    if saw_metrics and not saw_conversation:
        return [], "sdk-metrics"
    return [], "unknown"


def _largest_sessions(root: Path, n: int) -> list[Path]:
    """Return the N largest .jsonl files under root by file size, ≥ 50 KB."""
    candidates: list[tuple[int, Path]] = []
    for p in root.rglob("*.jsonl"):
        if "subagents" in p.parts:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < 50_000:
            continue
        candidates.append((size, p))
    candidates.sort(reverse=True)
    return [p for _, p in candidates[:n]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RA-1967 tao-context-vcc validator")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Directory to scan for jsonl transcripts",
    )
    parser.add_argument("-n", "--num-sessions", type=int, default=10)
    parser.add_argument("--threshold-pct", type=float, default=30.0)
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        sys.stderr.write(f"[fatal] {args.root} not a directory\n")
        return 2

    sessions = _largest_sessions(args.root, args.num_sessions)
    if not sessions:
        sys.stderr.write("[fatal] no eligible sessions found (>=50KB)\n")
        return 2

    count_tokens, token_label = _resolve_token_counter()
    print("# RA-1967 / tao-context-vcc validation")
    print(f"# Root: {args.root}")
    print(f"# Token counter: {token_label}")
    print(f"# Threshold: median pct_reduction >= {args.threshold_pct:.1f}%")
    print(f"# Sessions sampled: {len(sessions)}")
    print()
    print(
        f"{'session':<20} {'msgs_in':>8} {'msgs_out':>9} "
        f"{'tokens_in':>10} {'tokens_out':>11} {'pct':>7}  techniques"
    )

    rows: list[tuple] = []
    skipped_metrics = 0
    skipped_unknown = 0
    for path in sessions:
        sid = path.stem[:12]
        msgs_in, shape = _extract_messages(path)
        if shape == "sdk-metrics":
            sys.stderr.write(
                f"[validate] {sid}: no message content in SDK metrics shape — "
                "pointing at ~/.claude/projects/<encoded>/ instead is recommended\n"
            )
            skipped_metrics += 1
            continue
        if not msgs_in:
            sys.stderr.write(f"[skip] {sid}: shape={shape}, no messages\n")
            skipped_unknown += 1
            continue
        msgs_out, stats = compact(msgs_in)
        tokens_in = count_tokens(_flatten(msgs_in))
        tokens_out = count_tokens(_flatten(msgs_out))
        if tokens_in == 0:
            continue
        pct = 100.0 * (tokens_in - tokens_out) / tokens_in
        techniques = ",".join(
            f"{k}={v}" for k, v in stats.techniques_applied.items() if v
        )
        print(
            f"{sid:<20} {len(msgs_in):>8} {len(msgs_out):>9} "
            f"{tokens_in:>10} {tokens_out:>11} {pct:>6.1f}%  {techniques or '(none)'}"
        )
        rows.append((sid, len(msgs_in), tokens_in, tokens_out, pct, stats))

    print()
    if not rows:
        sys.stderr.write(
            f"[fatal] no valid session results "
            f"(skipped metrics={skipped_metrics}, unknown={skipped_unknown})\n"
        )
        return 1

    pcts = [r[4] for r in rows]
    med = statistics.median(pcts)
    mean = statistics.mean(pcts)
    total_in = sum(r[2] for r in rows)
    total_out = sum(r[3] for r in rows)
    overall_pct = 100.0 * (total_in - total_out) / total_in if total_in else 0.0

    print(
        f"AGGREGATE: n={len(rows)} median_pct={med:.1f} mean_pct={mean:.1f} "
        f"overall_pct={overall_pct:.1f} (total {total_in} -> {total_out})"
    )
    print()

    if med >= args.threshold_pct:
        print(f"VERDICT: GO — median {med:.1f}% >= threshold {args.threshold_pct:.1f}%")
        return 0
    print(f"VERDICT: NO-GO — median {med:.1f}% < threshold {args.threshold_pct:.1f}%")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
