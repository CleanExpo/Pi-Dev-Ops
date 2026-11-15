"""RA-8100 classifier (delivery_stage): spec tests T1, T3, T4, T5, T6, T7, T10 (classifier halves),
plus the record/finding shape. Pure inputs only: no network, no file, no collector call."""
from __future__ import annotations

import ast
import json
import subprocess
import sys

import pytest

from _delivery_reconcile_support import (
    ATO, FAKE_REVIEWER, NOW, PIDEV, REPO_ROOT, SHA_A, SHA_B, SHA_C, ago, error_item, merged_facts, mission,
    open_facts, orphan_item, review,
)

from app.server import delivery_stage as ds
from app.server.delivery_closure import Snapshot, Stage, can_finish, finding_key

GREEN_STAGES = {"review_wait", "approval_wait", "merge_ready", "merged", "deploying", "verified_live", "done",
                "tested"}
RECORD_KEYS = {"id", "kind", "project_id", "repo", "ref", "stage", "reason", "owner", "since", "age_source",
               "counted", "prs", "pr_head_sha", "reviewed_head_sha", "authorised_head_sha", "merge_sha",
               "deployed_sha", "verified_sha", "tests_passed", "acceptance_passed", "live_source_provable",
               "approval_identity_unverified"}
FINDING_KEYS = {"key", "mission_id", "code", "severity", "next_owner", "message", "ref", "repo", "since",
                "age_source", "url"}


def run(issue: dict | None, prs: list[dict] | None, *, repo: str = PIDEV, live: dict | None = None,
        first_seen: float | None = None) -> tuple[dict, list[dict]]:
    return ds.classify(issue, prs, live if live is not None else {"revision": None, "compare": {}}, NOW,
                       repo=repo, project_id="pi-dev-ops", first_seen=first_seen)


def codes(findings: list[dict]) -> list[str]:
    return [f["code"] for f in findings]


@pytest.fixture(autouse=True)
def _no_reviewers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAO_DELIVERY_HUMAN_REVIEWERS", raising=False)


# ── T1: the mission is recorded with its PR; an unlinked human PR is UNOWNED ──────────────────────
def test_t1_mission_recorded_with_its_pr_and_orphan_is_unowned() -> None:
    record, _ = run(mission(), [open_facts(7, check_done=0.5)])
    assert (record["id"], record["kind"], record["ref"]) == ("RA-1", "mission", "RA-1")
    assert record["prs"] == [{"repo": PIDEV, "number": 7, "state": "open"}]
    assert record["owner"] == "Test Owner" and record["stage"] == "review_wait"
    orphan, found = run(None, [orphan_item(9, created=2)])
    assert (orphan["id"], orphan["kind"], orphan["ref"]) == (f"pr:{PIDEV}#9", "orphan_pr", f"{PIDEV}#9")
    assert orphan["owner"] is None and orphan["stage"] == "building"
    assert codes(found) == ["UNOWNED"]
    assert found[0]["url"] == f"https://github.com/{PIDEV}/pull/9"


# ── T3: a failed CI or reviewer read is UNKNOWN + EVIDENCE_UNKNOWN, never a green stage ──────────
@pytest.mark.parametrize("prs, reason", [
    ([error_item(7, "unknown", "http_500")], "http_500"),
    ([error_item(7, "unknown", "malformed_list")], "malformed_list"),
    (None, "links_incomplete"),
])
def test_t3_failed_read_is_unknown_never_green(prs: list[dict] | None, reason: str) -> None:
    record, found = run(mission(), prs)
    assert record["stage"] == "unknown" and record["reason"] == reason
    assert record["stage"] not in GREEN_STAGES and record["tests_passed"] is False
    assert codes(found) == ["EVIDENCE_UNKNOWN"]
    assert found[0]["severity"] == "escalation" and found[0]["next_owner"] == "Test Owner"


@pytest.mark.parametrize("missing", ["check_runs", "status", "reviews"])
def test_t3_open_facts_without_a_read_are_unknown_not_empty(missing: str) -> None:
    facts = open_facts(7, check_done=0.5)
    facts[missing] = None
    record, found = run(mission(), [facts])
    assert record["stage"] == "unknown" and "EVIDENCE_UNKNOWN" in codes(found)


# ── T4: allow-listed approval on an older commit leaves REVIEW_WAIT + STALE_REVIEW_SHA ───────────
def test_t4_stale_review_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    facts = open_facts(7, head=SHA_A, check_done=0.5, reviews=[review(FAKE_REVIEWER, "APPROVED", SHA_B)])
    record, found = run(mission(), [facts])
    assert record["stage"] == "review_wait" and record["pr_head_sha"] == SHA_A
    assert codes(found) == ["STALE_REVIEW_SHA"]
    assert found[0]["severity"] == "reminder" and found[0]["next_owner"] == "Test Owner"
    assert found[0]["key"] == finding_key("RA-1", "review_wait", SHA_A, "STALE_REVIEW_SHA")
    snap = Snapshot(issue_id="RA-1", project_id="p", stage=Stage.REVIEW_WAIT, stage_since=NOW,
                    tests_passed=record["tests_passed"], pr_head_sha=record["pr_head_sha"],
                    reviewed_head_sha=record["reviewed_head_sha"],
                    authorised_head_sha=record["authorised_head_sha"], acceptance_passed=True)
    assert can_finish(snap) is False and record["reviewed_head_sha"] != SHA_A


# ── T5: missing commits are MISSING_COMMIT, never BUILDING ─────────────────────────────────────────
@pytest.mark.parametrize("item, reason", [
    (error_item(7, "missing_commit", "empty_head"), "empty_head"),
    (error_item(7, "missing_commit", "head_not_found"), "head_not_found"),
    (error_item(7, "missing_commit", "no_merge_sha"), "no_merge_sha"),
    (open_facts(7, head=""), "empty_head"),
    (merged_facts(7, merge=None), "no_merge_sha"),
])
def test_t5_missing_commit(item: dict, reason: str) -> None:
    record, found = run(mission(), [item])
    assert record["stage"] == "missing_commit" and record["reason"] == reason
    assert codes(found) == ["MISSING_COMMIT"]
    assert found[0]["severity"] == "escalation"


# ── T6: every key comes from finding_key (literal inputs, never the record's own fields) ─────────
def test_t6_every_key_equals_finding_key() -> None:
    cases = [
        (run(mission(), [error_item(7)]), {("EVIDENCE_UNKNOWN", finding_key("RA-1", "unknown", None,
                                                                           "EVIDENCE_UNKNOWN"))}),
        (run(mission(), [error_item(7, "missing_commit", "empty_head")]),
         {("MISSING_COMMIT", finding_key("RA-1", "unknown", None, "MISSING_COMMIT"))}),
        (run(mission(), [open_facts(7)]), {("STALE_24H", finding_key("RA-1", "review_wait", SHA_A, "STALE_24H"))}),
        (run(None, [orphan_item(9)]), {
            ("UNOWNED", finding_key(f"pr:{PIDEV}#9", "building", SHA_C, "UNOWNED")),
            ("UNOWNED_24H", finding_key(f"pr:{PIDEV}#9", "building", SHA_C, "UNOWNED_24H"))}),
        (ds.repo_findings(ATO, 2, None), {("NO_DEPLOY_SOURCE", finding_key(f"repo:{ATO}", "repo", "",
                                                                           "NO_DEPLOY_SOURCE"))}),
        (ds.repo_findings("CleanExpo/Synthex", 0, SHA_B), {
            ("LIVE_UNCONFIRMED", finding_key("repo:CleanExpo/Synthex", "repo", SHA_B, "LIVE_UNCONFIRMED"))}),
    ]
    for (_, found), expected in cases:
        assert {(f["code"], f["key"]) for f in found} == expected


def test_t6_unknown_head_comes_from_the_one_linked_pr() -> None:
    facts = open_facts(7, head=SHA_A)
    facts["reviews"] = None
    _, found = run(mission(), [facts])
    assert codes(found) == ["EVIDENCE_UNKNOWN"]
    assert found[0]["key"] == finding_key("RA-1", "unknown", SHA_A, "EVIDENCE_UNKNOWN")


# ── T7: checks green 72 h ago and no review raises a founder finding with its source time ────────
def test_t7_three_day_overdue_review_is_a_founder_finding() -> None:
    record, found = run(mission(started=100), [open_facts(7, check_done=72)])
    assert record["stage"] == "review_wait" and record["tests_passed"] is True
    founder = [f for f in found if f["severity"] == "founder"]
    assert founder and founder[0]["since"] == ago(72) and founder[0]["age_source"] == "check_completed_at"
    assert record["since"] == ago(72) and record["age_source"] == "check_completed_at"


# ── Shape: plain JSON, mission_id equals record id, no description text ─────────────────────────
@pytest.mark.parametrize("issue, prs, repo", [
    (mission(), [open_facts(7)], PIDEV),
    (mission(), [error_item(7)], PIDEV),
    (mission(state="completed", completed=2), [open_facts(7)], PIDEV),
    (mission(), [merged_facts(7)], ATO),
    (None, [orphan_item(9)], PIDEV),
])
def test_record_and_findings_are_plain_json(issue: dict | None, prs: list[dict], repo: str) -> None:
    record, found = run(issue, prs, repo=repo)
    text = json.dumps(record) + json.dumps(found)
    assert "SECRET-DESCRIPTION-MARKER" not in text and found
    assert set(record) == RECORD_KEYS and record["authorised_head_sha"] is None
    assert record["acceptance_passed"] is False
    for f in found:
        assert set(f) == FINDING_KEYS and f["mission_id"] == record["id"]
        assert not any(isinstance(v, float) for v in f.values())


def test_repo_record_shape_and_mission_id() -> None:
    record, found = ds.repo_findings(ATO, 3, None)
    json.dumps([record, found])
    assert record == {"id": f"repo:{ATO}", "kind": "repo", "repo": ATO, "ref": ATO, "stage": "repo",
                      "live_source": "none", "live_unconfirmed": None, "merged_unverifiable": 3, "counted": None}
    assert [f["mission_id"] for f in found] == [f"repo:{ATO}"] and set(found[0]) == FINDING_KEYS


# ── T10: the classifier imports nothing that writes or reaches the network ──────────────────────
WRITE_MODULES = ("supabase", "ticket_sweeper_write", "session_linear", "ship_gate", "telegram", "slack",
                 "linear_pulse", "delivery_collect_github")
STDLIB_OK = {"__future__", "os", "re", "datetime", "typing", "collections.abc", "dataclasses", "math"}
RELATIVE_OK = {"delivery_closure", "delivery_stage_facts", "delivery_collect_fields"}


@pytest.mark.parametrize("module", ["delivery_stage", "delivery_stage_facts"])
def test_t10_import_pulls_in_no_write_helper(module: str) -> None:
    code = f"import json, sys, app.server.{module}; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    mods = json.loads(out.stdout.strip().splitlines()[-1])
    assert [m for m in mods if m.startswith("app.") and any(w in m for w in WRITE_MODULES)] == []


@pytest.mark.parametrize("module", ["delivery_stage", "delivery_stage_facts"])
def test_t10_classifier_source_imports_only_pure_modules(module: str) -> None:
    path = REPO_ROOT / f"app/server/{module}.py"
    assert path.exists(), module
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= STDLIB_OK
        elif isinstance(node, ast.ImportFrom):
            assert (node.level == 1 and node.module in RELATIVE_OK) or (node.level == 0
                                                                         and node.module in STDLIB_OK)
        elif isinstance(node, ast.Name):
            assert node.id not in {"urlopen", "urllib", "requests", "httpx", "subprocess", "socket", "open"}
