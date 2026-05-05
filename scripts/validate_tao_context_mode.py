"""scripts/validate_tao_context_mode.py — RA-1969 validation harness.

CRITICAL: comparison is **context-mode vs vcc baseline**, NOT vs raw harness.
RA-1967 vcc already achieves median ~56% reduction out of the box. The board
memo threshold is median ≥40% ADDITIONAL reduction over that vcc baseline.

Approach (deterministic, no SDK calls):
    1. Build CodebaseIndex over --repo-root (default ./app/server).
    2. Load N hand-crafted questions from _context_mode_questions.json.
    3. For each question:
       baseline (vcc):   flatten ALL source files in scope into one mega-prompt
                         and run tao_context_vcc.compact() on it.
       treatment (mode): start from index summaries (compact), expand only the
                         expected_files for this question.
       pct_reduction = (vcc_tokens - mode_tokens) / vcc_tokens * 100
    4. Aggregate: median, mean, overall.
    5. Threshold: median ≥40%. Exit 0 if PASS, 1 otherwise.

Usage:
    python scripts/validate_tao_context_mode.py --repo-root . [--scope-dir app/server]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# build_index ticks once per file. The default TAO_MAX_ITERS=25 is sized for
# LLM loops, not file scans — bump it for the harness so the index is complete.
os.environ.setdefault("TAO_MAX_ITERS", "100000")

from app.server.tao_context_mode import build_index, expand  # noqa: E402
from app.server.tao_context_vcc import compact  # noqa: E402

_QUESTIONS_FILE = Path(__file__).parent / "_context_mode_questions.json"
_THRESHOLD_DEFAULT: float = 40.0


def _resolve_token_counter():
    try:
        import tiktoken  # type: ignore  # noqa: PLC0415

        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda t: len(enc.encode(t))), "tiktoken-cl100k_base"
    except Exception:
        sys.stderr.write("[validate] tiktoken unavailable — bytes/4 proxy.\n")
        return (lambda t: max(1, len(t.encode("utf-8")) // 4)), "bytes-div-4"


def _flatten_all_source(repo_root: Path, scope_dir: Path) -> str:
    """Concatenate every source file under scope_dir into one big string."""
    parts: list[str] = []
    for path in sorted(scope_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".py", ".ts", ".tsx", ".js", ".md"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(repo_root)
        parts.append(f"# === {rel} ===\n{text}")
    return "\n\n".join(parts)


def _compact_via_vcc(text: str) -> str:
    """Run vcc compact on a single mega-prompt by wrapping it as one user msg."""
    msgs = [{"role": "user", "content": text}]
    out, _ = compact(msgs)
    if not out:
        return ""
    content = out[0].get("content", "")
    if isinstance(content, list):
        return "\n".join(str(b.get("text", b)) for b in content)
    return str(content)


def _mode_context(index, expected_files: list[str], repo_root: Path) -> str:
    """Index summaries + on-demand expansion of expected_files."""
    summary_lines = ["# Codebase index (path — summary [symbols])"]
    for path, fs in sorted(index.summaries.items()):
        symbols = ", ".join(fs.symbols[:6])
        summary_lines.append(f"- {path} — {fs.summary} [{symbols}]")
    body_parts: list[str] = []
    for rel in expected_files:
        if rel in index.summaries:
            body_parts.append(f"# === {rel} ===\n{expand(index, rel)}")
        else:
            abs_p = (repo_root / rel).resolve()
            if abs_p.is_file():
                body_parts.append(f"# === {rel} ===\n{abs_p.read_text(encoding='utf-8', errors='replace')}")
    return "\n".join(summary_lines) + "\n\n" + "\n\n".join(body_parts)


def _print_table(rows: list[tuple]) -> None:
    headers = ("question", "vcc_tokens", "mode_tokens", "pct_reduction")
    widths = [
        max(len(headers[i]), max((len(str(r[i])) for r in rows), default=0))
        for i in range(len(headers))
    ]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))


def _truncate(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=str(_ROOT))
    p.add_argument("--scope-dir", default="app/server",
                   help="Subdir to use for the vcc baseline mega-prompt")
    p.add_argument("--threshold", type=float, default=_THRESHOLD_DEFAULT)
    p.add_argument("--questions", default=str(_QUESTIONS_FILE))
    args = p.parse_args(argv[1:])

    repo_root = Path(args.repo_root).resolve()
    scope_dir = (repo_root / args.scope_dir).resolve()
    if not scope_dir.is_dir():
        print(f"[validate] scope-dir not found: {scope_dir}", file=sys.stderr)
        return 1

    counter, counter_name = _resolve_token_counter()
    print("=" * 72)
    print("RA-1969 tao-context-mode validation")
    print("Comparison: context-mode vs **vcc baseline** (NOT raw harness).")
    print("vcc baseline (RA-1967, 2026-05-05): median 56.1% over raw.")
    print(f"Threshold: median ≥{args.threshold}% additional reduction over vcc.")
    print(f"Token counter: {counter_name}")
    print(f"Repo root:     {repo_root}")
    print(f"Scope dir:     {scope_dir}")
    print("=" * 72)

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    print(f"[validate] loaded {len(questions)} questions")

    print("[validate] building CodebaseIndex...")
    index = build_index(repo_root)
    print(f"[validate] indexed {len(index.summaries)} files, "
          f"{index.total_bytes_indexed} bytes")

    print("[validate] flattening + vcc-compacting baseline...")
    raw = _flatten_all_source(repo_root, scope_dir)
    vcc_compacted = _compact_via_vcc(raw)
    vcc_tokens_baseline = counter(vcc_compacted)
    print(f"[validate] vcc baseline: {vcc_tokens_baseline} tokens "
          f"(raw was {counter(raw)})")

    rows: list[tuple] = []
    pct_values: list[float] = []
    for q in questions:
        question = q["question"]
        expected = list(q.get("expected_files", []))
        mode_text = _mode_context(index, expected, repo_root)
        mode_tokens = counter(mode_text)
        if vcc_tokens_baseline <= 0:
            pct = 0.0
        else:
            pct = round(100.0 * (1.0 - mode_tokens / vcc_tokens_baseline), 2)
        rows.append((_truncate(question, 60), vcc_tokens_baseline, mode_tokens, pct))
        pct_values.append(pct)

    print()
    _print_table(rows)

    median_pct = round(statistics.median(pct_values), 2) if pct_values else 0.0
    mean_pct = round(statistics.mean(pct_values), 2) if pct_values else 0.0
    print()
    print(f"[validate] questions: {len(rows)}")
    print(f"[validate] vcc baseline tokens: {vcc_tokens_baseline}")
    print(f"[validate] median pct_reduction (mode vs vcc): {median_pct}%")
    print(f"[validate] mean pct_reduction:                  {mean_pct}%")

    if median_pct >= args.threshold:
        print(f"[validate] PASS — median {median_pct}% >= {args.threshold}%")
        return 0
    print(f"[validate] FAIL — median {median_pct}% < {args.threshold}% "
          "(per board memo: WATCH not REJECT)")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
