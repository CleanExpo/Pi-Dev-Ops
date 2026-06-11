#!/usr/bin/env python3
"""Validate a forward-planner structured plan JSON.

Checks the schema essentials so a plan isn't handed to the autonomous loop
half-formed:
  - required top-level fields present
  - >= 15 moves (the foresight horizon)
  - move ids unique
  - depends_on / unlocks / branch targets reference existing move ids
  - dependency graph is acyclic (no circular prerequisites)
  - every move.satisfies references a real win-condition id
  - every win-condition id is satisfied by at least one move (else: red-team miss)

Exit code 0 = valid (warnings allowed), 1 = invalid (errors found).

Usage:
    python validate_plan.py <path-to-plan.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _has_cycle(moves: dict[str, list[str]]) -> list[str]:
    """Return a cycle path if the depends_on graph has one, else []."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {m: WHITE for m in moves}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        color[node] = GREY
        stack.append(node)
        for dep in moves.get(node, []):
            if dep not in color:
                continue  # dangling ref handled elsewhere
            if color[dep] == GREY:
                return stack[stack.index(dep):] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        color[node] = BLACK
        stack.pop()
        return []

    for m in moves:
        if color[m] == WHITE:
            found = visit(m)
            if found:
                return found
    return []


def validate(plan: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field in ("project_id", "goal", "win_condition", "moves"):
        if field not in plan:
            errors.append(f"missing required top-level field: {field!r}")
    if errors:
        return errors, warnings

    moves = plan.get("moves", [])
    if not isinstance(moves, list):
        return ["'moves' must be a list"], warnings

    if len(moves) < 15:
        warnings.append(
            f"only {len(moves)} moves — forward-planner targets a 15+ move horizon; "
            "are deliverables bundled too coarsely?"
        )

    ids = [m.get("id") for m in moves]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"duplicate move ids: {dupes}")
    id_set = set(ids)

    # reference integrity
    dep_graph: dict[str, list[str]] = {}
    for m in moves:
        mid = m.get("id", "<no-id>")
        deps = m.get("depends_on", []) or []
        dep_graph[mid] = deps
        for d in deps:
            if d not in id_set:
                errors.append(f"move {mid}: depends_on unknown move {d!r}")
        for u in m.get("unlocks", []) or []:
            if u not in id_set:
                errors.append(f"move {mid}: unlocks unknown move {u!r}")
        for b in m.get("branches", []) or []:
            for tgt in (b.get("then", []) or []) + ([b.get("reconverge")] if b.get("reconverge") else []):
                if tgt not in id_set:
                    errors.append(f"move {mid}: branch target {tgt!r} is not a known move")

    cycle = _has_cycle(dep_graph)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    # win-condition coverage
    wc_ids = {wc.get("id") for wc in plan.get("win_condition", [])}
    satisfied: set[str] = set()
    for m in moves:
        for wc in m.get("satisfies", []) or []:
            satisfied.add(wc)
            if wc not in wc_ids:
                errors.append(f"move {m.get('id')}: satisfies unknown win-condition {wc!r}")
    for wc in wc_ids:
        if wc not in satisfied:
            warnings.append(
                f"win-condition {wc!r} is not satisfied by any move — likely a red-team miss "
                "(something you declared 'done' means but didn't plan to build)"
            )

    # linear routing
    unrouted = [m.get("id") for m in moves if not (m.get("linear") or {}).get("project_id")]
    if unrouted:
        warnings.append(
            f"{len(unrouted)} move(s) have no Linear routing — they can't be auto-filed as tickets: "
            + ", ".join(str(x) for x in unrouted[:10])
            + (" …" if len(unrouted) > 10 else "")
        )

    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python validate_plan.py <path-to-plan.json>", file=sys.stderr)
        return 2
    path = argv[1]
    if not Path(path).exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    try:
        plan = _load(path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1

    errors, warnings = validate(plan)

    moves = plan.get("moves", []) if isinstance(plan.get("moves"), list) else []
    branch_pts = sum(1 for m in moves if m.get("is_branch_point"))
    print(f"plan: {plan.get('project_id', '?')} — {plan.get('goal', '')[:60]}")
    print(f"  moves: {len(moves)} | branch points: {branch_pts} | "
          f"win conditions: {len(plan.get('win_condition', []))}")

    for w in warnings:
        print(f"  WARN: {w}")
    for e in errors:
        print(f"  ERROR: {e}")

    if errors:
        print("INVALID — fix errors before handing to the loop.")
        return 1
    print("VALID" + (" (with warnings)" if warnings else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
