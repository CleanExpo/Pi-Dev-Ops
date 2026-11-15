"""RA-8100 D55: every row of ``delivery_invariants.ANSWERS``, driven through the real reader.

Each row has one planted answer whose fields are each in their own domain and contradict each other (or
what was asked). For every row: the planted answer breaks that row and no other; the real reader refuses
it with the row's reason code; and with that one row taken out of the table the reader accepts it, so the
test is known to fail without the rule. A row with no planted answer fails the coverage test.
"""
from __future__ import annotations

import ast
import copy

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, REPO_ROOT, SHA_A, SHA_B, SHA_C, compare_answer, good_pr_paths, install_fakes, merged_pull, open_pull,
    sweep_path,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg
from app.server import delivery_invariants as inv
from app.server.delivery_collect_fields import IDENTITY

BASE = f"/repos/{ATO}"
ASKED = {"compare": {"base": SHA_A, "head": SHA_B}, "review": {"created": "2026-11-14T01:00:00Z"}}  # open_pull
REVIEW = {"id": 1, "user": {"login": "someone", "type": "User"}, "state": "COMMENTED", "commit_id": SHA_A,
          "submitted_at": "2026-11-14T03:00:00Z"}
GOOD = {"compare": compare_answer(SHA_A, SHA_B, "ahead"), "pull": open_pull(5), "pulls_list": open_pull(5),
        "status": {"state": "pending", "total_count": 0, "sha": SHA_A}, "review": REVIEW,
        "check_run": {"id": 1, "status": "completed", "conclusion": "success", "completed_at": "2026-11-14T02:00:00Z",
                      "head_sha": SHA_A}}
SAME = compare_answer(SHA_A, SHA_A, "identical")  # a true answer, about ONE commit

# row -> (kind, the planted answer)
PLANTED: dict[str, tuple[str, dict]] = {
    "compare_fields": ("compare", {**GOOD["compare"], "ahead_by": True}),
    "compare_label": ("compare", {**GOOD["compare"], "behind_by": 1}),  # says ahead, counts say diverged
    "compare_list_whole": ("compare", {**GOOD["compare"], "total_commits": 251}),  # GitHub stopped at 250
    "compare_ends_on_head": ("compare", {**GOOD["compare"], "commits": [{"sha": SHA_C}]}),
    "compare_merge_base": ("compare", SAME),  # Codex round 7: identical, for two different commits asked
    "pull_merged_has_time": ("pull", {**open_pull(5), "state": "closed", "merged": True}),
    "pull_merged_is_closed": ("pull", {**merged_pull(5), "state": "open"}),
    "pull_merged_after_created": ("pull", {**merged_pull(5), "created_at": "2026-11-15T11:00:00Z",
                                           "merged_at": "2026-11-15T10:00:00Z"}),
    "listed_pull_is_open": ("pulls_list", {**open_pull(5), "state": "closed"}),
    "status_none_is_pending": ("status", {"state": "success", "total_count": 0, "sha": SHA_A}),
    "review_submitted_unless_pending": ("review", {**REVIEW, "state": "APPROVED", "submitted_at": None}),
    "review_not_before_its_pull": ("review", {**REVIEW, "submitted_at": "2020-01-01T00:00:00Z"}),
    "check_run_finished_together": ("check_run", {**GOOD["check_run"], "completed_at": None}),  # green, no finish time
}
MORE = [  # other faces of the same rows
    ("compare_merge_base", "compare", {**GOOD["compare"], "merge_base_commit": {"sha": SHA_C}}),
    ("compare_merge_base", "compare", {**compare_answer(SHA_A, SHA_B, "behind"), "merge_base_commit": {"sha": SHA_A}}),
    ("compare_merge_base", "compare", {**compare_answer(SHA_A, SHA_B, "diverged"), "merge_base_commit": {"sha": SHA_A}}),
    ("compare_label", "compare", {**SAME, "status": "ahead", "merge_base_commit": {"sha": SHA_A}}),
    ("compare_list_whole", "compare", {**GOOD["compare"], "commits": [], "total_commits": 0}),
    ("compare_fields", "compare", {**GOOD["compare"], "merge_base_commit": {"sha": "nope"}}),
    ("listed_pull_is_open", "pulls_list", {**open_pull(5), "merged": True}),
    ("listed_pull_is_open", "pulls_list", {**open_pull(5), "merged_at": "2026-11-14T03:00:00Z"}),
    ("compare_list_whole", "compare", {**GOOD["compare"], "ahead_by": 7}),  # seven ahead, one listed
    ("compare_list_whole", "compare", {**GOOD["compare"], "commits": [{"sha": SHA_B}] * 2, "total_commits": 2, "ahead_by": 2}),
    ("compare_list_whole", "compare", {**GOOD["compare"], "commits": [{"sha": SHA_A}, {"sha": SHA_B}], "total_commits": 2,
                                       "ahead_by": 2}),  # the base asked is itself listed
    ("check_run_finished_together", "check_run", {**GOOD["check_run"], "status": "in_progress"}),
    ("check_run_finished_together", "check_run", {**GOOD["check_run"], "conclusion": None}),
    ("review_not_before_its_pull", "review", {**REVIEW, "submitted_at": "2026-11-14T00:59:59Z"}),
    ("status_none_is_pending", "status", {"state": "failure", "total_count": 0, "sha": SHA_A}),
]


def _read(monkeypatch: pytest.MonkeyPatch, kind: str, body: dict) -> str | None:
    """The reason the real reader refuses ``body`` with, or None when it accepts it."""
    st = install_fakes(monkeypatch)
    st.gh.update(good_pr_paths(ATO, 5))
    tick = dc.Tick(allowed=ALLOWED)
    paths = {"pull": f"{BASE}/pulls/5", "status": f"{BASE}/commits/{SHA_A}/status",
             "review": f"{BASE}/pulls/5/reviews?per_page=100&page=1",
             "check_run": f"{BASE}/commits/{SHA_A}/check-runs?per_page=100&page=1"}
    wrap = {"review": lambda b: [b], "check_run": lambda b: {"total_count": 1, "check_runs": [b]}}
    try:
        if kind == "compare":
            st.gh[f"{BASE}/compare/{SHA_A}...{SHA_B}"] = copy.deepcopy(body)
            dg.compare_status(ATO, SHA_A, SHA_B, tick=tick)
        elif kind == "pulls_list":
            st.gh[sweep_path(ATO)] = [copy.deepcopy(body)]
            dg.open_prs(ATO, tick=tick)
        else:
            st.gh[paths[kind]] = wrap.get(kind, lambda b: b)(copy.deepcopy(body))
            dg.pr_evidence(ATO, 5, tick=tick)
    except dc.Unknown as exc:
        return exc.reason
    return None


def _rows(kind: str) -> tuple:
    return inv.ANSWERS[kind].get("rows", ())


def test_every_row_has_a_planted_answer_and_every_answer_kind_an_entry() -> None:
    assert set(PLANTED) == {name for kind in inv.ANSWERS for name, _fields, _rule, _holds in _rows(kind)}
    assert set(inv.ANSWERS) == set(IDENTITY)  # one entry per outside answer the collector reads
    for kind, entry in inv.ANSWERS.items():
        assert ("why" in entry) != ("rows" in entry), kind  # rules, or the written reason there are none
        assert all(name and rule for name, _fields, rule, _holds in _rows(kind)) and ("rows" not in entry or entry["code"])


@pytest.mark.parametrize("kind", sorted(GOOD))
def test_the_control_answer_is_accepted(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    assert inv.answer_broken(kind, GOOD[kind], **ASKED.get(kind, {})) == []
    assert _read(monkeypatch, kind, GOOD[kind]) is None


@pytest.mark.parametrize("row", sorted(PLANTED))
def test_a_contradictory_answer_breaks_its_row_and_the_reader_refuses_it(monkeypatch: pytest.MonkeyPatch,
                                                                        row: str) -> None:
    kind, body = PLANTED[row]
    assert inv.answer_broken(kind, body, **ASKED.get(kind, {})) == [row]  # this rule and no other
    assert _read(monkeypatch, kind, body) == inv.ANSWERS[kind]["code"]


@pytest.mark.parametrize("row", sorted(PLANTED))
def test_without_its_row_the_contradiction_is_accepted(monkeypatch: pytest.MonkeyPatch, row: str) -> None:
    """The mutation: this row taken out of the table. The planted answer then passes, so the test above
    is known to fail when the rule is missing."""
    kind, body = PLANTED[row]
    kept = tuple(r for r in _rows(kind) if r[0] != row)
    monkeypatch.setitem(inv.ANSWERS, kind, {**inv.ANSWERS[kind], "rows": kept})
    assert _read(monkeypatch, kind, body) != inv.ANSWERS[kind]["code"]


@pytest.mark.parametrize("row,kind,body", MORE, ids=[f"{m[0]}-{i}" for i, m in enumerate(MORE)])
def test_other_faces_of_a_row_are_refused(monkeypatch: pytest.MonkeyPatch, row: str, kind: str, body: dict) -> None:
    assert row in inv.answer_broken(kind, body, **ASKED.get(kind, {}))
    assert _read(monkeypatch, kind, body) == inv.ANSWERS[kind]["code"]


def test_a_rule_that_cannot_be_evaluated_is_broken_not_passed() -> None:
    assert inv.answer_problem("compare", None, base=SHA_A, head=SHA_B) == "compare_mismatch"
    assert inv.answer_problem("compare", {"status": "ahead"}, base=SHA_A, head=SHA_B) == "compare_mismatch"
    assert inv.answer_problem("status", {}) == "malformed_status" and inv.answer_problem("commit", {}) is None


@pytest.mark.parametrize("status", ["identical", "ahead", "behind", "diverged"])
def test_each_compare_status_agrees_only_with_its_own_commits(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    """A true answer for each status is accepted; the same answer under any other status label is refused."""
    head = SHA_A if status == "identical" else SHA_B
    body = compare_answer(SHA_A, head, status)
    assert inv.answer_broken("compare", body, base=SHA_A, head=head) == []
    for other in {"identical", "ahead", "behind", "diverged"} - {status}:
        assert inv.answer_broken("compare", {**body, "status": other}, base=SHA_A, head=head), other
    if status != "identical":
        assert _read(monkeypatch, "compare", body) is None


def test_the_reader_applies_every_kind_that_has_rows() -> None:
    source = (REPO_ROOT / "app/server/delivery_collect_github.py").read_text(encoding="utf-8")
    for kind, entry in inv.ANSWERS.items():
        assert (f'_agree("{kind}"' in source) == ("rows" in entry), kind


def test_the_module_is_pure() -> None:
    allowed = {"delivery_invariants": {(0, "__future__"), (0, "collections.abc"), (0, "typing"),
                                       (1, "delivery_collect_fields"), (1, None)},  # (1, None): its own checks
               "delivery_invariant_checks": {(0, "__future__"), (1, "delivery_collect_fields")}}
    for module, imports in allowed.items():
        tree = ast.parse((REPO_ROOT / f"app/server/{module}.py").read_text(encoding="utf-8"))
        assert {(n.level, n.module) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} == imports, module
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import)]
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module is None for a in n.names}
        assert names <= {"delivery_invariant_checks"}
