#!/usr/bin/env python3
"""scripts/validate_tao_context_prune.py — RA-1990 manual-verification harness.

Runs prune() THEN compact() on saved Claude Code transcripts. Reports
per-session pct_reduction relative to the BASELINE (vcc compact alone).

The acceptance threshold from RA-1990 spec: median ≥ 70% (vs vcc's 56%,
14pp marginal). Note this is total reduction (raw → prune+vcc), not the
marginal over vcc — interpreted as "the chained pipeline beats the spec
floor for total compaction".

Same corpus + token-counter conventions as `validate_tao_context_vcc.py`.

Usage:
    python3 scripts/validate_tao_context_prune.py --root ~/.claude/projects -n 10
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.server.tao_context_prune import prune  # noqa: E402
from app.server.tao_context_vcc import compact  # noqa: E402


def _resolve_token_counter():
    try:
        import tiktoken  # type: ignore  # noqa: PLC0415

        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda t: len(enc.encode(t))), "tiktoken-cl100k_base"
    except Exception:
        sys.stderr.write("[validate] tiktoken unavailable — bytes/4 proxy\n")
        return (lambda t: max(1, len(t.encode("utf-8")) // 4)), "bytes-div-4"


def _flatten(messages: list[dict]) -> str:
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
    parser = argparse.ArgumentParser(description="RA-1990 prune+vcc validator")
    parser.add_argument(
        "--root", type=Path,
        default=Path.home() / ".claude" / "projects",
    )
    parser.add_argument("-n", "--num-sessions", type=int, default=10)
    parser.add_argument(
        "--threshold-pct", type=float, default=70.0,
        help="Median total reduction (raw -> prune+vcc). Spec floor 70%%.",
    )
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        sys.stderr.write(f"[fatal] {args.root} not a directory\n")
        return 2

    sessions = _largest_sessions(args.root, args.num_sessions)
    if not sessions:
        sys.stderr.write("[fatal] no eligible sessions found (>=50KB)\n")
        return 2

    count_tokens, token_label = _resolve_token_counter()
    print("# RA-1990 / tao-context-prune validation (prune → vcc)")
    print(f"# Root: {args.root}")
    print(f"# Token counter: {token_label}")
    print(f"# Threshold: median total pct_reduction >= {args.threshold_pct:.1f}%")
    print(f"# Sessions sampled: {len(sessions)}")
    print()
    print(
        f"{'session':<14} {'msgs':>5} "
        f"{'tk_in':>9} {'tk_vcc':>9} {'tk_pv':>9} "
        f"{'vcc%':>6} {'pv%':>7} {'Δ%':>6}  techniques"
    )

    rows: list[tuple] = []
    skipped_metrics = 0
    skipped_unknown = 0
    for path in sessions:
        sid = path.stem[:12]
        msgs_in, shape = _extract_messages(path)
        if shape == "sdk-metrics":
            skipped_metrics += 1
            continue
        if not msgs_in:
            skipped_unknown += 1
            continue
        # Baseline: vcc alone
        msgs_vcc, vcc_stats = compact(msgs_in)
        # Pipeline: prune then vcc
        msgs_pruned, prune_stats = prune(msgs_in)
        msgs_pv, _vcc_stats2 = compact(msgs_pruned)
        tokens_in = count_tokens(_flatten(msgs_in))
        tokens_vcc = count_tokens(_flatten(msgs_vcc))
        tokens_pv = count_tokens(_flatten(msgs_pv))
        if tokens_in == 0:
            continue
        vcc_pct = 100.0 * (tokens_in - tokens_vcc) / tokens_in
        pv_pct = 100.0 * (tokens_in - tokens_pv) / tokens_in
        delta_pct = pv_pct - vcc_pct
        techs = ",".join(
            f"{k}={v}" for k, v in prune_stats.techniques_applied.items() if v
        )
        print(
            f"{sid:<14} {len(msgs_in):>5} "
            f"{tokens_in:>9} {tokens_vcc:>9} {tokens_pv:>9} "
            f"{vcc_pct:>5.1f}% {pv_pct:>6.1f}% {delta_pct:>+5.1f}%  {techs or '(none)'}"
        )
        rows.append((sid, tokens_in, tokens_vcc, tokens_pv,
                      vcc_pct, pv_pct, delta_pct))

    print()
    if not rows:
        sys.stderr.write(
            f"[fatal] no valid session results "
            f"(skipped metrics={skipped_metrics}, unknown={skipped_unknown})\n"
        )
        return 1

    pv_pcts = [r[5] for r in rows]
    deltas = [r[6] for r in rows]
    med_pv = statistics.median(pv_pcts)
    med_delta = statistics.median(deltas)
    mean_pv = statistics.mean(pv_pcts)
    total_in = sum(r[1] for r in rows)
    total_pv = sum(r[3] for r in rows)
    overall_pv_pct = (
        100.0 * (total_in - total_pv) / total_in if total_in else 0.0
    )

    print(
        f"AGGREGATE: n={len(rows)} "
        f"median_pv_pct={med_pv:.1f} mean_pv_pct={mean_pv:.1f} "
        f"overall_pv_pct={overall_pv_pct:.1f} "
        f"median_delta_over_vcc={med_delta:+.1f}pp"
    )
    print()

    if med_pv >= args.threshold_pct:
        print(f"VERDICT: GO — median total {med_pv:.1f}% >= {args.threshold_pct:.1f}%")
        return 0
    print(
        f"VERDICT: WATCH — median total {med_pv:.1f}% < {args.threshold_pct:.1f}%. "
        f"Marginal over vcc baseline: {med_delta:+.1f}pp."
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
