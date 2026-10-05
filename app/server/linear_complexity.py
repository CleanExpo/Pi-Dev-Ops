"""Estimate a Linear GraphQL query's complexity before sending it (RA-7910).

Linear refuses any query over 10,000 points with HTTP 400. Its published rule
(linear.app/developers/rate-limiting): each property is 0.1 point, each object is
1 point, and a connection multiplies its children's points by its pagination
argument, or 50 when none is given. On 04/10/2026 the mesh self-claim query reached
~10,050 at 25 issues a page, so every claim failed and the fleet claimed nothing.

This walks the query text; it has no schema, so it treats a selection that contains
``nodes`` as a connection. Budgets in tests sit well under Linear's ceiling to absorb
the difference between this estimate and Linear's own count.
"""
from __future__ import annotations

import json
import re

LINEAR_MAX_COMPLEXITY = 10_000
_DEFAULT_PAGE = 50
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*|\d+|[{}()]|\$|[^\s]')


def _skip_args(tokens: list[str], i: int) -> tuple[int, int | None]:
    """Skip a parenthesised argument list at tokens[i]; return (next index, first:N)."""
    depth, first = 0, None
    while i < len(tokens):
        tok = tokens[i]
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
            if depth == 0:
                return i + 1, first
        elif (tok == "first" and depth == 1 and i + 2 < len(tokens)
              and tokens[i + 1] == ":" and tokens[i + 2].isdigit()):
            first = int(tokens[i + 2])
        i += 1
    raise ValueError("unbalanced parentheses in query")


def _selection(tokens: list[str], i: int) -> tuple[float, float | None, int]:
    """Selection set opening at tokens[i] == '{'.

    Returns (cost of its fields, cost of ONE ``nodes`` entry or None, next index).
    """
    total, per_node, i = 0.0, None, i + 1
    while tokens[i] != "}":
        name, i = tokens[i], i + 1
        first = None
        if i < len(tokens) and tokens[i] == "(":
            i, first = _skip_args(tokens, i)
        if i < len(tokens) and tokens[i] == "{":
            flat, nodes, i = _selection(tokens, i)
            if name == "nodes":
                per_node = 1 + flat  # each node is an object; the parent multiplies it
                continue
            if nodes is not None:
                flat += nodes * (first if first is not None else _DEFAULT_PAGE)
            total += 1 + flat
        else:
            total += 0.1
    return total, per_node, i + 1


def estimate(query: str) -> float:
    """Estimated Linear complexity points for ``query`` (operation header ignored)."""
    tokens = _TOKEN.findall(query)
    cost, _, _ = _selection(tokens, tokens.index("{"))
    return cost


def error_detail(exc: Exception) -> str:
    """``": <Linear's errors[].message>"`` for an HTTP error from Linear, else ``""``.

    Linear's 400 body names the cause, such as a complexity refusal; the fleet failed
    blind for hours without it (RA-7910). Only the messages, never the request.
    """
    read = getattr(exc, "read", None)
    if getattr(exc, "code", None) is None or not callable(read):
        return ""
    try:
        body = json.loads(read() or b"{}")
    except Exception:  # noqa: BLE001
        return ": <unreadable error body>"
    errors = body.get("errors") if isinstance(body, dict) else None
    msgs = [str(x.get("message", ""))[:300] for x in errors or [] if isinstance(x, dict)]
    return ": " + ("; ".join(m for m in msgs if m) or "<no error message>")
