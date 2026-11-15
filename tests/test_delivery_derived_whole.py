"""RA-8100 D48 pre-screen: two more faces of the old kind, closed by design rather than by instance.

1. A DERIVED subject. A repo's record is worked out from other reads (its missions' records and, for some
   repos, a Vercel read). It is emitted and proven only when every one of those inputs was read whole this
   tick; otherwise the repo is held and its stored record and alert stay exactly as they were. Before, a
   failed Vercel read wrote ``live_unconfirmed: None`` over the stored value, and a mission whose pull read
   failed was counted as "0 merged missions", both on a tick reported complete.
2. A REQUESTED field. Every field the Linear query asks for must be present in every node: an absent key
   is a cut answer, never "null". The query and the presence check are built from one list
   (``delivery_collect_fields.ISSUE_FIELDS``), so a field cannot be requested without being required.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, PIDEV, linear_page, merged_paths, open_pull, pr_paths, reg_entry, run, setup_tick, sweep_path,
    tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_collect_fields as fields

RA = "CleanExpo/RestoreAssist"  # a repo whose live source is ``live_unconfirmed``: its record needs a Vercel read
SHA_V = "d" * 40


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _deploys(sha: str) -> dict:
    return {"deployments": [{"state": "READY", "created": 5, "target": "production",
                             "meta": {"githubCommitSha": sha}}]}


def _vercel_ticks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, second: object) -> tuple[dict, dict, dict]:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ra", RA, vercel="prj")])
    st.gh[sweep_path(RA)] = []
    st.gql_pages += [linear_page([])]
    st.vc["*"] = _deploys(SHA_V)
    assert run(st)["complete"] is True
    first = _state(st)
    st.gql_pages += [linear_page([])]
    st.vc["*"] = second
    return first, run(st), _state(st)


def test_a_failed_vercel_read_leaves_the_stored_repo_record_untouched(monkeypatch: pytest.MonkeyPatch,
                                                                    tmp_path: Path) -> None:
    first, out, state = _vercel_ticks(monkeypatch, tmp_path, RuntimeError("boom"))
    rid = f"repo:{RA}"
    assert first["missions"][rid]["live_unconfirmed"] == SHA_V  # positive control: tick 1 stored the revision
    assert state["missions"][rid] == first["missions"][rid]  # held: not rewritten, not even its last_seen
    assert out["vercel_unreadable"] == 1 and rid in out["not_refreshed_ids"]
    assert {a["code"] for a in state["alerts"].values()} == {"LIVE_UNCONFIRMED"}


def test_positive_control_a_whole_vercel_read_rewrites_the_repo_record(monkeypatch: pytest.MonkeyPatch,
                                                                      tmp_path: Path) -> None:
    first, out, state = _vercel_ticks(monkeypatch, tmp_path, _deploys("e" * 40))
    rid = f"repo:{RA}"
    assert state["missions"][rid]["live_unconfirmed"] == "e" * 40 and rid not in out["not_refreshed_ids"]


def _merged_count_ticks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fail: bool) -> tuple[dict, dict, dict]:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", ATO)])  # ATO has no deploy source
    st.gh[sweep_path(ATO)] = []
    st.gh.update(merged_paths(ATO, 5))
    st.gql_pages += [linear_page([tick_issue("RA-1", ((ATO, 5),))])]
    assert run(st)["complete"] is True
    first = _state(st)
    if fail:
        st.gh[f"/repos/{ATO}/pulls/5"] = RuntimeError("x")
    st.gql_pages += [linear_page([tick_issue("RA-1", ((ATO, 5),))])]
    return first, run(st), _state(st)


def _no_deploy(state: dict) -> list[str]:
    return [a["message"] for a in state["alerts"].values() if a["code"] == "NO_DEPLOY_SOURCE"]


def test_a_repo_count_is_not_rewritten_from_a_mission_that_was_not_read_whole(monkeypatch: pytest.MonkeyPatch,
                                                                             tmp_path: Path) -> None:
    first, out, state = _merged_count_ticks(monkeypatch, tmp_path, fail=True)
    rid = f"repo:{ATO}"
    assert "1 merged" in _no_deploy(first)[0]  # positive control: tick 1 counted the merged mission
    assert state["missions"]["RA-1"]["stage"] == "unknown" and "RA-1" in out["not_refreshed_ids"]
    assert _no_deploy(state) == _no_deploy(first)  # never "0 merged missions" from a failed read
    assert state["missions"][rid] == first["missions"][rid] and rid in out["not_refreshed_ids"]


def test_positive_control_whole_missions_refresh_the_repo_record(monkeypatch: pytest.MonkeyPatch,
                                                                tmp_path: Path) -> None:
    first, out, state = _merged_count_ticks(monkeypatch, tmp_path, fail=False)
    rid = f"repo:{ATO}"
    assert rid not in out["not_refreshed_ids"] and out["not_refreshed_ids"] == []
    assert state["missions"][rid]["last_seen"] == state["last_tick"] and _no_deploy(state) == _no_deploy(first)


@pytest.mark.parametrize("missing", sorted(fields.ISSUE_FIELDS))
def test_a_node_missing_a_requested_field_is_a_cut_answer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                         missing: str) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pd", PIDEV)])
    st.gh.update({sweep_path(PIDEV): [open_pull(7)], **pr_paths(PIDEV, 7)})
    node = {"createdAt": "2026-11-13T00:00:00Z", **tick_issue("RA-1", ((PIDEV, 7),))}
    assert set(node) == set(fields.ISSUE_FIELDS)  # the fake node is a whole answer before the key is removed
    del node[missing]
    st.gql_pages += [linear_page([node])]
    out = run(st)
    assert out["complete"] is False and out["incomplete"] == {"pd": "malformed_page"}
    assert "RA-1" not in _state(st)["missions"]  # nothing was classified from the cut node


def test_positive_control_a_whole_node_is_classified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pd", PIDEV)])
    st.gh.update({sweep_path(PIDEV): [open_pull(7)], **pr_paths(PIDEV, 7)})
    st.gql_pages += [linear_page([tick_issue("RA-1", ((PIDEV, 7),))])]
    out = run(st)
    assert out["complete"] is True and _state(st)["missions"]["RA-1"]["stage"] != "unknown"


def test_the_query_asks_for_exactly_the_fields_the_check_requires() -> None:
    """One list builds both: the node selection in the query text is ``ISSUE_FIELDS``, key for key."""
    selection = " ".join(f"{name}{args}" for name, args in fields.ISSUE_FIELDS.items())
    assert collect._MISSIONS_QUERY.count(selection) == 1
    assert {"id", "identifier", "startedAt", "completedAt", "description", "state", "assignee",
            "attachments"} <= set(fields.ISSUE_FIELDS)
