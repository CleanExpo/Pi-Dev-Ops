"""RA-8100 D48 part 1: ONE wholeness value (founder ruling 15/11/2026, the strict rule).

``complete`` means "the tick's scope is known" and has one owner, ``store.complete``. The merge takes no
``complete`` argument: the checkpoint, the removal rule and the stored summary all read the value derived
from the scope. A mission link list that did not arrive whole makes the whole tick incomplete, and the
summary names that mission with a reason. The per-source flags have one writer, ``Run.cut``, which records
the subject and reason in the same step.
"""
from __future__ import annotations

import ast
import inspect
import json
from datetime import timedelta
from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    NOW, PIDEV, REPO_ROOT, linear_page, open_pull, reg_entry, run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_gather as gather
from app.server import delivery_reconcile_store as store

ENTRIES = [reg_entry("pi-dev-ops", PIDEV)]
MODULES = sorted((REPO_ROOT / "app/server").glob("delivery_reconcile*.py"))


def _tick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, links_whole: bool) -> tuple[dict, dict, dict]:
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    st.gh[sweep_path(PIDEV)] = [open_pull(9)]
    st.gql_pages += [linear_page([tick_issue("RA-1", links_whole=links_whole)])]
    out = run(st)
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    return out, state, dr.status_snapshot(st.path, NOW + timedelta(minutes=1))


def test_a_cut_link_list_makes_the_tick_incomplete_and_names_the_mission(monkeypatch: pytest.MonkeyPatch,
                                                                          tmp_path: Path) -> None:
    """Codex round 6 finding 1, by its reproduction: the tick was stored and shown as complete."""
    out, state, tile = _tick(monkeypatch, tmp_path, links_whole=False)
    assert out["persisted"] is True and out["complete"] is False
    assert state["summary"]["complete"] is False and state["checkpoint"]["last_complete"] is None
    assert state["summary"]["incomplete"] == {"RA-1": "links_incomplete"}
    assert tile["complete"] is False and tile["counts"]["incomplete"] == {"RA-1": "links_incomplete"}


def test_positive_control_whole_link_lists_give_a_complete_tick(monkeypatch: pytest.MonkeyPatch,
                                                               tmp_path: Path) -> None:
    out, state, tile = _tick(monkeypatch, tmp_path, links_whole=True)
    assert out["persisted"] is True and out["complete"] is True and state["summary"]["incomplete"] == {}
    assert state["checkpoint"]["last_complete"] == NOW.timestamp() and tile["complete"] is True


def test_the_merge_takes_no_complete_argument() -> None:
    assert "complete" not in inspect.signature(store.apply_tick).parameters
    assert "complete" not in inspect.signature(gather.gather).parameters
    assert store.complete(None) is False and store.complete(set()) is True and store.complete({"M"}) is True


@pytest.mark.parametrize("scope,expected", [(None, False), (set(), True), ({"M"}, True)])
def test_checkpoint_and_summary_follow_the_scope_and_nothing_else(scope: set | None, expected: bool) -> None:
    summary = {**gather.new_summary(NOW), "complete": not expected}  # a caller's own value is never kept
    state, _ = store.apply_tick(store.empty_state(), [], [], 5.0, scope=scope, summary=summary)
    assert state["summary"]["complete"] is expected
    assert state["checkpoint"]["last_complete"] == (5.0 if expected else None)
    assert summary["complete"] is (not expected)  # the merge is pure: the caller's dict is untouched


def _complete_writes(source: str) -> list[tuple[str, int]]:
    """(enclosing function, line) of every place the key ``complete`` is given a value other than the
    literal False: a dict display, a subscript store or a keyword argument."""
    found: list[tuple[str, int]] = []
    for fn in [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            values: list[ast.expr] = []
            if isinstance(node, ast.Dict):
                values = [v for k, v in zip(node.keys, node.values)
                          if isinstance(k, ast.Constant) and k.value == "complete"]
            elif isinstance(node, ast.Assign):
                values = [node.value for t in node.targets if isinstance(t, ast.Subscript)
                          and isinstance(t.slice, ast.Constant) and t.slice.value == "complete"]
            elif isinstance(node, ast.Call):
                values = [kw.value for kw in node.keywords if kw.arg == "complete"]
            found += [(fn.name, node.lineno) for v in values
                      if not (isinstance(v, ast.Constant) and v.value is False)]
    return found


# The value's two homes: the store derives it from the scope, and the tile may only narrow the stored one.
OWNERS = {"apply_tick", "build"}


def test_only_the_owner_gives_complete_a_value() -> None:
    writers = {name for path in MODULES for name, _ in _complete_writes(path.read_text(encoding="utf-8"))}
    assert writers == OWNERS


def test_negative_control_the_walk_catches_a_second_writer() -> None:
    planted = ("def sneaky(summary, a, b):\n    summary['complete'] = a and b\n"
               "def also(a):\n    return {'complete': a}\n"
               "def honest():\n    return {'complete': False}\n")
    assert {name for name, _ in _complete_writes(planted)} == {"sneaky", "also"}


def _attribute_writes(source: str, names: set[str]) -> set[str]:
    tree = ast.parse(source)
    return {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for node in ast.walk(fn)
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(t, ast.Attribute) and t.attr in names}


def _incomplete_writes(source: str) -> set[str]:
    """Functions that store into ``...["incomplete"][...]``."""
    return {fn.name for fn in ast.walk(ast.parse(source)) if isinstance(fn, ast.FunctionDef)
            for node in ast.walk(fn) if isinstance(node, ast.Assign) for t in node.targets
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Subscript)
            and isinstance(t.value.slice, ast.Constant) and t.value.slice.value == "incomplete"}


def test_one_writer_flips_a_source_and_names_the_reason() -> None:
    sources = [path.read_text(encoding="utf-8") for path in MODULES]
    old_flags = {"linear_whole", "sweep_whole", "links_whole"}
    assert not any(flag in source for source in sources for flag in old_flags)  # the three hand-kept flags are gone
    assert set().union(*(_incomplete_writes(s) for s in sources)) == {"cut"}
    assert set().union(*(_attribute_writes(s, {"cuts"}) for s in sources)) <= {"cut"}


def test_negative_control_a_second_reason_writer_is_caught() -> None:
    planted = "def sneaky(run):\n    run.summary['incomplete']['x'] = 'y'\n    run.cuts = set()\n"
    assert _incomplete_writes(planted) == {"sneaky"} and _attribute_writes(planted, {"cuts"}) == {"sneaky"}


def test_every_cut_source_makes_the_scope_unknown() -> None:
    """Whichever scope-defining list was cut, the scope is None, so the tick is incomplete: one rule."""
    for source in ("linear", "sweep", "links"):
        run_ = gather.Run({}, None, "k", NOW, gather.new_summary(NOW))  # type: ignore[arg-type]
        run_.cut(source, "subject", "reason")
        assert gather._scope(run_, []) is None and run_.summary["incomplete"] == {"subject": "reason"}
        assert run_.uncut(source) is False and run_.uncut(*({"linear", "sweep", "links"} - {source})) is True
