"""RA-8100 D55: the list of rules between fields is COMPLETE BY CHECK, not by claim.

The pre-screen of 15a669d3 found rules that were simply missing from ``delivery_invariants``: nothing made a
missing rule visible. Two checks do now, and neither keeps a field list of its own:
1. every field read from an outside answer (the field inventory) and every key of every stored dict (the
   schema) is named by a row, or by ``ALONE`` with the reason no rule relates it; never by both;
2. a row names exactly the fields its check reads: the check's source is parsed (through every helper it
   calls) and the keys it reads must be the fields the row names. A row cannot claim a field it ignores,
   and a check cannot read a field its row does not name.
Each check is shown to fail on a planted gap.
"""
from __future__ import annotations

import ast

from _delivery_reconcile_support import REPO_ROOT
from test_delivery_field_inventory import INVENTORY

from app.server import delivery_invariants as inv
from app.server import delivery_reconcile_schema as schema

MODULES = ("delivery_invariants", "delivery_invariant_checks")
ASKED = {"base", "head", "created"}  # what the reader passes beside the answer: not fields of the answer
PATH = {"missions", "alerts", "summary", "checkpoint", "kind", "user"}  # the way to an entry, and its kind


def answer_fields() -> set[str]:
    return {f"{source}.{field}" for source, field, *_ in INVENTORY}


def stored_fields() -> set[str]:
    placed = schema.RECORDS["mission"]
    assert set(schema.RECORDS["orphan_pr"]) == set(placed)  # one shape, two kinds
    dicts = {"state": schema.STATE, "checkpoint": schema.CHECKPOINT, "record": placed, "repo": schema.RECORDS["repo"],
             "pr": schema.PR, "alert": schema.ALERT, "summary": schema.SUMMARY}
    return {f"{owner}.{key}" for owner, keys in dicts.items() for key in keys}


def rows() -> list[tuple]:
    return [row for entry in inv.ANSWERS.values() for row in entry.get("rows", ())] + list(inv.STATE) \
        + list(inv.READINGS)


def named(table: list[tuple]) -> set[str]:
    return {field for _name, fields, *_ in table for field in fields.split()}


def alone(table: dict[str, str]) -> list[str]:
    return [field for fields in table.values() for field in fields.split()]


def gaps(fields: set[str], table: list[tuple], apart: dict[str, str]) -> dict[str, list[str]]:
    """What check 1 finds: fields nobody names, names that are no field, and fields named twice."""
    lone = alone(apart)
    return {"unnamed": sorted(fields - named(table) - set(lone)), "unknown": sorted((named(table) | set(lone)) - fields),
            "both": sorted(named(table) & set(lone)), "twice_alone": sorted({f for f in lone if lone.count(f) > 1})}


def test_every_field_is_named_by_a_row_or_stands_alone_with_a_reason() -> None:
    assert gaps(answer_fields() | stored_fields(), rows(), inv.ALONE) == {"unnamed": [], "unknown": [], "both": [],
                                                                         "twice_alone": []}
    assert all(reason.strip() for reason in inv.ALONE)


def test_negative_control_a_field_nobody_names_is_reported() -> None:
    fields = answer_fields() | stored_fields()
    cut = {reason: text.replace("record.owner", "") for reason, text in inv.ALONE.items()}
    assert gaps(fields, rows(), cut)["unnamed"] == ["record.owner"]  # dropped from ALONE, in no row
    assert gaps(fields | {"pull.auto_merge"}, rows(), inv.ALONE)["unnamed"] == ["pull.auto_merge"]  # a new read
    assert gaps(fields | {"record.signed_off"}, rows(), inv.ALONE)["unnamed"] == ["record.signed_off"]  # a new key
    doubled = {**inv.ALONE, "again": "record.stage"}
    assert gaps(fields, rows(), doubled)["both"] == ["record.stage"]
    assert gaps(fields, [("r", "record.stagee", "", None)], inv.ALONE)["unknown"] == ["record.stagee"]


def _trees() -> dict[str, ast.Module]:
    return {m: ast.parse((REPO_ROOT / f"app/server/{m}.py").read_text(encoding="utf-8")) for m in MODULES}


def definitions(trees: dict[str, ast.Module]) -> dict[str, ast.AST]:
    """Every module-level function and assignment of the two modules, by name."""
    out: dict[str, ast.AST] = {}
    for tree in trees.values():
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                out[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(target, ast.Name):
                        out[target.id] = node.value
    return out


def keys_read(node: ast.AST, defs: dict[str, ast.AST], seen: set[str] | None = None) -> set[str]:
    """Every key ``node`` reads: ``x["k"]``, ``x.get("k")`` and ``"k" in x``, through every helper it names."""
    seen = set() if seen is None else seen
    out: set[str] = set()
    for sub in ast.walk(node):
        const = None
        if isinstance(sub, ast.Subscript):
            const = sub.slice
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get" and sub.args:
            const = sub.args[0]
        elif isinstance(sub, ast.Compare) and isinstance(sub.ops[0], (ast.In, ast.NotIn)):
            const = sub.left
        if isinstance(const, ast.Constant) and isinstance(const.value, str):
            out.add(const.value)
        name = sub.id if isinstance(sub, ast.Name) else (sub.attr if isinstance(sub, ast.Attribute) else None)
        if name in defs and name not in seen and name not in ("STATE", "ANSWERS"):
            seen.add(name)
            out |= keys_read(defs[name], defs, seen)
    return out


def row_nodes(trees: dict[str, ast.Module]) -> dict[str, ast.AST]:
    """The check expression of every row, by row name, from the tables' own source."""
    defs = definitions(trees)
    tables = [defs["STATE"], defs["READINGS"]] + [value for entry in defs["ANSWERS"].values for key, value in zip(entry.keys, entry.values)
                                if key.value == "rows"]
    return {row.elts[0].value: row.elts[3] for table in tables for row in table.elts}


def misnamed(name: str, fields: str, check: ast.AST, defs: dict[str, ast.AST]) -> tuple[list[str], list[str]]:
    """(keys the check reads that the row does not name, fields the row names that the check never reads)."""
    segments = {part for field in fields.split() for part in field.split(".")[1:]}
    read = keys_read(check, defs) - ASKED
    return sorted(read - segments - PATH), sorted(segments - read - PATH)


def test_every_row_names_exactly_the_fields_its_check_reads() -> None:
    trees = _trees()
    defs, nodes = definitions(trees), row_nodes(trees)
    table = rows()
    assert sorted(nodes) == sorted(name for name, *_ in table)  # every row of both tables was found in the source
    for name, fields, _rule, _holds in table:
        assert misnamed(name, fields, nodes[name], defs) == ([], []), name


def test_negative_control_a_row_that_misnames_its_fields_is_reported() -> None:
    trees = _trees()
    defs, nodes = definitions(trees), row_nodes(trees)
    assert misnamed("x", "record.stage", nodes["refused_has_a_reason"], defs) == (["reason"], [])  # reads more
    assert misnamed("x", "record.stage record.reason record.owner", nodes["refused_has_a_reason"], defs) == ([], ["owner"])
    assert misnamed("x", "compare.status", nodes["compare_merge_base"], defs) == (["merge_base_commit", "sha"], [])
    assert misnamed("x", "summary.complete summary.incomplete", nodes["complete_has_no_reason"], defs) == (["error"], [])
    planted = ast.parse('lambda r: r["stage"] == "done" and helper(r)\ndef helper(r):\n    return r.get("owner")')
    assert keys_read(planted.body[0], {"helper": planted.body[1]}) == {"stage", "owner"}  # helpers are followed
