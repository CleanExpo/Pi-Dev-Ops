"""RA-8100 B5g: an answer is evidence only about the commit it names. A check run whose ``head_sha``, or a
combined status whose ``sha``, names another commit than the head asked about is rejected, the way
``pull_mismatch`` and ``commit_mismatch`` already are. Absent or malformed is not a match either."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, PIDEV, SHA_A, SHA_C, good_pr_paths, install_fakes, linear_page, open_pull, pr_paths, reg_entry,
    run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg

CHECKS = f"/repos/{ATO}/commits/{SHA_A}/check-runs?per_page=100&page=1"
STATUS = f"/repos/{ATO}/commits/{SHA_A}/status"
_ABSENT = object()


def _reason(monkeypatch: pytest.MonkeyPatch, path: str, field: str | None, value: object) -> str | None:
    st = install_fakes(monkeypatch)
    st.gh.update(good_pr_paths(ATO, 5))
    if field is not None:
        target = st.gh[path]["check_runs"][0] if path == CHECKS else st.gh[path]
        if value is _ABSENT:
            target.pop(field, None)
        else:
            target[field] = value
    try:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    except dc.Unknown as exc:
        return exc.reason
    return None


def test_control_answers_about_the_head_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _reason(monkeypatch, CHECKS, None, None) is None


@pytest.mark.parametrize("value", [SHA_C, _ABSENT, None, "", "not-a-sha", SHA_A.upper()[:39]])
def test_a_check_run_about_another_commit_is_rejected(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    assert _reason(monkeypatch, CHECKS, "head_sha", value) == "check_run_mismatch"


@pytest.mark.parametrize("value", [SHA_C, _ABSENT, None, "", "not-a-sha"])
def test_a_combined_status_about_another_commit_is_rejected(monkeypatch: pytest.MonkeyPatch, value: object) -> None:
    assert _reason(monkeypatch, STATUS, "sha", value) == "status_mismatch"


def test_the_upper_case_head_is_the_same_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _reason(monkeypatch, STATUS, "sha", SHA_A.upper()) is None


def test_a_green_answer_about_another_commit_never_passes_the_tests(monkeypatch: pytest.MonkeyPatch,
                                                                    tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update(pr_paths(PIDEV, 7))
    st.gh[f"/repos/{PIDEV}/commits/{SHA_A}/status"] = {"state": "success", "total_count": 1, "sha": SHA_C}
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7),))]))
    out = run(st)
    rec = json.loads(Path(st.path).read_text(encoding="utf-8"))["missions"]["RA-1"]
    assert (rec["stage"], rec["reason"], rec["tests_passed"]) == ("unknown", "status_mismatch", False)
    assert "RA-1" in out["not_refreshed_ids"]
