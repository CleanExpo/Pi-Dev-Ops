"""RA-8100 B5: a merged pull request counts only after its merge commit has been read."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, HTTP404, SHA_B, install_fakes, linear_page, merged_pull, reg_entry, run, setup_tick, sweep_path,
    tick_issue,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg

PULL = f"/repos/{ATO}/pulls/5"
COMMIT = f"/repos/{ATO}/commits/{SHA_B}"


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    return install_fakes(monkeypatch)


def test_merged_merge_commit_404_is_missing_commit(fakes: SimpleNamespace) -> None:
    fakes.gh.update({PULL: merged_pull(5), COMMIT: HTTP404("not found")})
    with pytest.raises(dc.MissingCommit) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "merge_not_found"


def test_merged_merge_commit_failed_read_is_unknown(fakes: SimpleNamespace) -> None:
    fakes.gh.update({PULL: merged_pull(5), COMMIT: RuntimeError("down")})
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert not isinstance(err.value, dc.MissingCommit)


def test_merged_merge_commit_budget_cut_is_budget_exhausted(fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    fakes.gh.update({PULL: merged_pull(5), COMMIT: {"sha": SHA_B}})
    monkeypatch.setitem(dc.BUDGETS, "github", 1)
    with pytest.raises(dc.BudgetExhausted):
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))


def test_merged_with_readable_commit_makes_two_requests(fakes: SimpleNamespace) -> None:
    fakes.gh.update({PULL: merged_pull(5), COMMIT: {"sha": SHA_B}})
    facts = dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert facts["state"] == "merged" and facts["merge_sha"] == SHA_B
    assert fakes.github == [PULL, COMMIT]


def test_closed_unmerged_reads_no_commit(fakes: SimpleNamespace) -> None:
    fakes.gh[PULL] = {**merged_pull(5), "merged": False, "merge_commit_sha": None}
    assert dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))["state"] == "closed"
    assert fakes.github == [PULL]


@pytest.mark.parametrize("failure,stage", [(HTTP404("nf"), "missing_commit"), (RuntimeError("down"), "unknown")])
def test_tick_unreadable_merge_commit_is_never_merged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception, stage: str,
) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", ATO)])
    st.gh[sweep_path(ATO)] = []
    st.gh[f"/repos/{ATO}/pulls/4"] = merged_pull(4)
    st.gh[f"/repos/{ATO}/commits/{SHA_B}"] = failure
    st.gql_pages.append(linear_page([tick_issue("RA-3", ((ATO, 4),))]))
    run(st)
    import json
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    assert state["missions"]["RA-3"]["stage"] == stage
    codes = {a["code"] for a in state["alerts"].values() if a["mission_id"] == "RA-3"}
    assert "LIVE_CANNOT_VERIFY" not in codes
    assert not [c for c in codes if c.startswith("DEPLOY")]
