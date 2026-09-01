"""tests/test_mesh_gate_read_safety.py — the gate that stops a sixth instance (RA-7405).

`test_mesh_read_failures.py` proves the five read sites now behave. This file
is the reason a sixth does not appear.

RA-7392 fixed one endpoint that rendered a failed Supabase read as empty lists.
Five more instances were then found in the same file — not because five authors
were careless, but because the shape was available and nothing objected: `_sb`
returns `(status, body)` and the parser took the BODY alone, so
`_, body = _sb("GET", …)` was the natural call and the status went in the bin.

Two structural invariants, both asserted over the parsed module rather than its
text, since a regex would also match the idiom quoted in a docstring — this
sentence included.

It lives in `tests/` rather than `.github/scripts/` deliberately: a new CI job
creates a check name that is not in branch protection until an admin adds it,
whereas a test rides the already-required `Python (pytest)` check and binds on
the first PR.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTE = Path(__file__).resolve().parents[1] / "app" / "server" / "routes" / "mesh.py"


def _sb_calls_discarding_status(tree: ast.AST) -> list:
    """Assignments of the form `_, x = _sb(...)` — the exact defect shape.

    An `ast` walk rather than a regex, matching `function_length_lint.py`'s
    approach: a regex over source would also match the idiom inside a comment
    or a docstring describing it, which this very file contains.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Tuple):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") in ("_sb", "_get")):
            continue
        first = node.targets[0].elts[0]
        if isinstance(first, ast.Name) and first.id == "_":
            found.append(node.lineno)
    return found


def test_no_read_site_discards_the_supabase_status():
    """THE GATE. Reintroducing `_, body = _sb("GET", …)` fails here.

    Verified to fail against a tree with the idiom restored, not merely
    observed to pass against the fixed one.
    """
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    lines = _sb_calls_discarding_status(tree)
    assert not lines, (
        f"{ROUTE.name} discards the Supabase status at line(s) {lines}. "
        "Read through `mesh_fleet.read(_get, path)`, which cannot be called "
        "without the status. See RA-7405."
    )


def test_the_gate_detects_the_defect_shape():
    """GREEN CONTROL for the gate itself.

    Without this, a matcher that found nothing anywhere would pass the test
    above on a broken file and read exactly like a clean one — which is the
    failure mode this whole ticket family is about.
    """
    bad = ast.parse('def f():\n    _, body = _sb("GET", "t")\n    return body\n')
    assert _sb_calls_discarding_status(bad) == [2]


def test_the_gate_does_not_flag_a_legitimate_status_check():
    """GREEN CONTROL 2 — writes legitimately bind the status and drop the body
    (`status, _ = _sb("POST", …)`). Flagging those would push authors to work
    around the gate rather than through it."""
    ok = ast.parse('def f():\n    status, _ = _sb("POST", "t", {})\n    return status\n')
    assert _sb_calls_discarding_status(ok) == []


def test_the_duplicate_parser_is_gone():
    """`mesh.py::_rows` and `mesh_fleet.parse_rows` both parsed PostgREST rows;
    only the latter sees the status. Two parsers drift, and that drift is how
    the fixed endpoint and its five unfixed siblings coexisted in one file."""
    names = {n.name for n in ast.walk(ast.parse(ROUTE.read_text(encoding="utf-8")))
             if isinstance(n, ast.FunctionDef)}
    assert "_rows" not in names, "the status-blind parser is back; use mesh_fleet.read"
