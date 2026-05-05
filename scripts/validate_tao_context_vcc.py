"""scripts/validate_tao_context_vcc.py — RA-1967 manual-verification harness.

Walks a directory of saved TAO sessions (jsonl files in
`.harness/agent-sdk-metrics/` by default), runs `compact()` on the loaded
messages, and prints a per-session table plus an aggregate row.

Exits 0 when median pct_reduction ≥ 30%, else 1.

Token counting prefers `tiktoken` (cl100k_base) for a closer Claude proxy.
Falls back to `len(text.encode('utf-8')) / 4` when tiktoken is unavailable
and logs the fallback to stderr.

Usage:
    python scripts/validate_tao_context_vcc.py [DIR]

DIR defaults to `.harness/agent-sdk-metrics`.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

# Make the app importable when run as a top-level script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.server.tao_context_vcc import compact  # noqa: E402


def _resolve_token_counter():
    """Return a callable text -> int. Prefers tiktoken; falls back to bytes/4."""
    try:
        import tiktoken  # type: ignore  # noqa: PLC0415

        enc = tiktoken.get_encoding("cl100k_base")

        def count(text: str) -> int:
            return len(enc.encode(text))

        return count, "tiktoken-cl100k_base"
    except Exception:
        sys.stderr.write(
            "[validate] tiktoken unavailable — falling back to bytes/4 proxy.\n"
        )

        def count(text: str) -> int:
            return max(1, len(text.encode("utf-8")) // 4)

        return count, "bytes-div-4"


def _flatten(messages: list[dict]) -> str:
    parts: list[str] = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for blk in c:
                if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                    parts.append(blk["text"])
                else:
                    parts.append(str(blk))
        else:
            parts.append(str(c))
    return "\n".join(parts)


def _load_session(path: Path) -> list[dict]:
    """Read a jsonl file and return rows that look like SDK messages."""
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "role" in obj and "content" in obj:
            rows.append(obj)
    return rows


def _row(session: str, tokens_in: int, tokens_out: int, techniques: dict[str, int]) -> tuple:
    pct = 0.0 if tokens_in <= 0 else round(100.0 * (1.0 - tokens_out / tokens_in), 2)
    technique_str = ", ".join(f"{k}={v}" for k, v in sorted(techniques.items())) or "—"
    return (session, tokens_in, tokens_out, pct, technique_str)


def _print_table(rows: list[tuple]) -> None:
    headers = ("session", "tokens_in", "tokens_out", "pct_reduction", "techniques_applied")
    widths = [
        max(len(headers[i]), max((len(str(r[i])) for r in rows), default=0))
        for i in range(len(headers))
    ]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else _ROOT / ".harness" / "agent-sdk-metrics"
    if not target.exists() or not target.is_dir():
        print(f"[validate] directory not found: {target}", file=sys.stderr)
        return 1

    counter, counter_name = _resolve_token_counter()
    print(f"[validate] token counter: {counter_name}")
    print(f"[validate] scanning: {target}")

    rows: list[tuple] = []
    pct_values: list[float] = []
    for path in sorted(target.glob("*.jsonl")):
        msgs = _load_session(path)
        if not msgs:
            continue
        before = counter(_flatten(msgs))
        compacted, stats = compact(msgs)
        after = counter(_flatten(compacted))
        rows.append(_row(path.name, before, after, stats.techniques_applied))
        if before > 0:
            pct_values.append(100.0 * (1.0 - after / before))

    if not rows:
        print("[validate] no SDK-message jsonl rows found in directory.")
        return 1

    _print_table(rows)

    median_pct = round(statistics.median(pct_values), 2) if pct_values else 0.0
    total_in = sum(r[1] for r in rows)
    total_out = sum(r[2] for r in rows)
    aggregate_pct = (
        round(100.0 * (1.0 - total_out / total_in), 2) if total_in > 0 else 0.0
    )
    print()
    print(f"[validate] sessions: {len(rows)}")
    print(f"[validate] median pct_reduction: {median_pct}%")
    print(f"[validate] aggregate tokens_in -> out: {total_in} -> {total_out} ({aggregate_pct}%)")

    threshold = float(os.environ.get("TAO_VCC_VALIDATE_THRESHOLD", "30.0"))
    if median_pct >= threshold:
        print(f"[validate] PASS — median {median_pct}% >= {threshold}%")
        return 0
    print(f"[validate] FAIL — median {median_pct}% < {threshold}%")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
