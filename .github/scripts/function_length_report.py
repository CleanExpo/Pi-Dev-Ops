#!/usr/bin/env python3
"""The `--report` diagnostic for function_length_lint.py.

Split out because it is not the gate. It re-derives the PLR0915 comparison table
in the gate's module docstring — the evidence for measuring lines rather than
statements — and nothing in the pass/fail path calls it. Keeping it alongside the
gate pushed that file past the 300-line convention it exists to enforce.

Imported lazily from `function_length_lint.main`, so the two modules do not form
an import cycle.

    python3 .github/scripts/function_length_lint.py --report
"""
from __future__ import annotations

import ast
from pathlib import Path


def report() -> int:
    """Re-derive the PLR0915 comparison in function_length_lint's docstring."""
    from function_length_lint import LIMIT, _walk, measure, tracked_python_files

    sizes, _ = measure()
    stmt_counts: dict[str, int] = {}
    for path in tracked_python_files():
        try:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        collected: dict[str, tuple[int, int, str]] = {}
        _walk(tree, "", path, collected)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                n = sum(1 for x in ast.walk(node) if isinstance(x, ast.stmt)) - 1
                for key, meta in collected.items():
                    if meta[1] == node.lineno:
                        stmt_counts[key] = n

    over = {k for k, v in sizes.items() if v[0] > LIMIT}
    print(f"functions: {len(sizes)} | over {LIMIT} lines: {len(over)}")
    for thr in (50, 40, 30, 20):
        caught = sum(1 for k in over if stmt_counts.get(k, 0) > thr)
        false = sum(
            1 for k, v in sizes.items()
            if v[0] <= LIMIT and stmt_counts.get(k, 0) > thr
        )
        pct = 100 * caught // len(over) if over else 0
        print(f"  max-statements={thr:<3} catches {caught:>4}/{len(over)} = {pct:>3}%  "
              f"| flags {false} already-compliant")
    return 0
