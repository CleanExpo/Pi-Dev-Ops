"""RA-8100 D55: the contradictions an independent pre-screen got past the first list of rules (15a669d3).

Each one is driven through the real entry (the reader, or ``save``), beside a control that is accepted, so
the test fails when its rule is missing and cannot pass by refusing everything. They were run against
15a669d3 first and failed there (evidence/build/red-first-prescreen-15a669d3.log).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, NOW, PIDEV, SHA_A, SHA_B, compare_answer, good_pr_paths, install_fakes, open_pull, sweep_path,
)
from _delivery_stored_support import planted, stored

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg
from app.server import delivery_reconcile_store as store

BASE, T = f"/repos/{ATO}", NOW.timestamp()
RUNS = f"{BASE}/commits/{SHA_A}/check-runs?per_page=100&page=1"
REVIEWS = f"{BASE}/pulls/5/reviews?per_page=100&page=1"
AHEAD = compare_answer(SHA_A, SHA_B, "ahead")


def _read(monkeypatch: pytest.MonkeyPatch, call: str = "evidence", **paths: object) -> str | None:
    """The reason the real reader refuses with, or None when it accepts every answer."""
    st = install_fakes(monkeypatch)
    st.gh.update({**good_pr_paths(ATO, 5), f"{BASE}/compare/{SHA_A}...{SHA_B}": AHEAD, sweep_path(ATO): [open_pull(5)]})
    st.gh.update(paths)
    tick = dc.Tick(allowed=ALLOWED)
    try:
        {"evidence": lambda: dg.pr_evidence(ATO, 5, tick=tick), "sweep": lambda: dg.open_prs(ATO, tick=tick),
         "compare": lambda: dg.compare_status(ATO, SHA_A, SHA_B, tick=tick)}[call]()
    except dc.Unknown as exc:
        return exc.reason
    return None


def _run(status: str, conclusion: str | None, done: str | None) -> dict:
    return {RUNS: {"total_count": 1, "check_runs": [{"id": 1, "status": status, "conclusion": conclusion,
                                                     "completed_at": done, "head_sha": SHA_A}]}}


def _review(at: str | None, state: str = "APPROVED") -> dict:
    return {REVIEWS: [{"id": 1, "user": {"login": "someone", "type": "User"}, "state": state, "commit_id": SHA_A,
                       "submitted_at": at}]}


@pytest.mark.parametrize("change", [
    {"ahead_by": 7},  # says seven commits ahead, lists one
    {"commits": [{"sha": SHA_A}, {"sha": SHA_B}], "total_commits": 2, "ahead_by": 2},  # lists the base itself
    {"commits": [{"sha": SHA_B}, {"sha": SHA_B}], "total_commits": 2, "ahead_by": 2},  # lists one commit twice
], ids=["count", "base_listed", "duplicate"])
def test_a_compare_list_that_disagrees_with_its_count_is_refused(monkeypatch: pytest.MonkeyPatch, change: dict) -> None:
    path = f"{BASE}/compare/{SHA_A}...{SHA_B}"
    assert _read(monkeypatch, "compare") is None  # the control: the true answer
    assert _read(monkeypatch, "compare", **{path: {**AHEAD, **change}}) == "compare_mismatch"


@pytest.mark.parametrize("status,conclusion,done", [
    ("completed", "success", None), ("completed", None, "2026-11-14T02:00:00Z"),
    ("in_progress", "success", None), ("queued", None, "2026-11-14T02:00:00Z")])
def test_a_check_run_whose_status_conclusion_and_time_disagree_is_refused(
        monkeypatch: pytest.MonkeyPatch, status: str, conclusion: str | None, done: str | None) -> None:
    assert _read(monkeypatch, **_run("in_progress", None, None)) is None  # the controls: running, and finished
    assert _read(monkeypatch, **_run("completed", "success", "2026-11-14T02:00:00Z")) is None
    assert _read(monkeypatch, **_run(status, conclusion, done)) == "malformed_check_run"


def test_a_review_dated_before_its_pull_was_created_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _read(monkeypatch, **_review("2026-11-14T01:00:00Z")) is None  # the control: the pull's own instant
    assert _read(monkeypatch, **_review("2020-01-01T00:00:00Z")) == "malformed_review"


def test_a_listed_open_pull_with_a_merge_time_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _read(monkeypatch, "sweep") is None
    merged = {**open_pull(5), "merged_at": "2026-11-14T03:00:00Z"}
    assert _read(monkeypatch, "sweep", **{sweep_path(ATO): [merged]}) == "malformed_pull"


def _saved(tmp_path: Path, state: dict) -> bool:
    return store.save(tmp_path / "s.json", state)


def _alert(code: str, severity: str) -> dict:
    return stored({"key": "k", "mission_id": "RA-1", "code": code, "severity": severity, "ref": "RA-1"}, at=T, alert=True)


def test_a_refused_record_with_no_alert_is_never_stored(tmp_path: Path) -> None:
    record = stored({"id": "RA-1", "stage": "unknown", "reason": "http_500", "since": "2026-11-14T00:00:00Z",
                     "age_source": "startedAt"}, at=T)
    alert = {"k": _alert("EVIDENCE_UNKNOWN", "escalation")}
    assert _saved(tmp_path, planted({"RA-1": record}, alert, at=T, complete=True)) is True  # the control
    assert _saved(tmp_path, planted({"RA-1": record}, at=T, complete=True)) is False
    wrong = {"k": _alert("UNOWNED", "reminder")}  # an alert, but not the one a refused record always raises
    assert _saved(tmp_path, planted({"RA-1": record}, wrong, at=T, complete=True)) is False


def test_a_tally_of_findings_no_stored_alert_carries_is_never_stored(tmp_path: Path) -> None:
    tally = {"by_severity": {"founder": 1}, "by_code": {"UNOWNED_24H": 1}, "founder_or_critical": ["RA-1"]}
    alert = {"k": _alert("UNOWNED_24H", "founder")}
    assert _saved(tmp_path, planted(alerts=alert, at=T, complete=True, **tally)) is True  # the control
    assert _saved(tmp_path, planted(at=T, complete=True, **tally)) is False
    other = {"k": {**_alert("UNOWNED_24H", "founder"), "ref": "RA-2"}}  # the top list names a ref no alert has
    assert _saved(tmp_path, planted(alerts=other, at=T, complete=True, **tally)) is False


OPEN = [{"repo": PIDEV, "number": 1, "state": "open"}]
PLACED = {"since": "2026-11-14T00:00:00Z", "pr_head_sha": SHA_A, "prs": OPEN}
GOOD = {"id": "RA-2", "stage": "approval_wait", "age_source": "review_submitted_at", "tests_passed": True,
        "reviewed_head_sha": SHA_A, **PLACED}


@pytest.mark.parametrize("record", [
    {"id": "RA-2", "stage": "merged", "age_source": "merged_at", "merge_sha": SHA_B, "deployed_sha": SHA_B,
     "verified_sha": SHA_B, **PLACED},  # merged and verified, and its only pull says open
    {"id": f"pr:{PIDEV}#3", "kind": "orphan_pr", "stage": "merged", "age_source": "merged_at", "merge_sha": SHA_B,
     "since": "2026-11-14T00:00:00Z"},  # a pull no mission links is never placed past building
    {**GOOD, "reviewed_head_sha": None},  # waiting for approval with no approved head
    {**GOOD, "tests_passed": False},  # waiting for approval with checks that are not green
    {**GOOD, "age_source": "merged_at"},  # aged from a source its stage never uses
], ids=["merged_but_open", "orphan_merged", "approval_no_review", "approval_not_green", "wrong_age_source"])
def test_a_record_whose_stage_contradicts_its_own_fields_is_never_stored(tmp_path: Path, record: dict) -> None:
    assert _saved(tmp_path, planted({"RA-2": stored(GOOD, at=T)}, at=T, complete=True)) is True  # the control
    assert _saved(tmp_path, planted({record["id"]: stored(record, at=T)}, at=T, complete=True)) is False
