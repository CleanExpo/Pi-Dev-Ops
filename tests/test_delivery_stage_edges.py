"""RA-8100 classifier edge tests: E1, E2, E3, E7, E8, E9, F4, F5, F6, F7, G2, G3, G5 (classifier and
repo_findings halves). Reviewer logins are fake; no test touches the network or a stored state."""
from __future__ import annotations

from datetime import datetime

import pytest

from _delivery_reconcile_support import (
    ATO, FAKE_REVIEWER, NOW, PIDEV, SHA_A, SHA_B, SHA_C, ago, closed_facts, error_item, merged_facts, mission,
    open_facts, orphan_item, review,
)

from app.server import delivery_collect
from app.server import delivery_stage as ds

SYNTHEX = "CleanExpo/Synthex"
CONTAINED = {"revision": SHA_C, "compare": {SHA_B: "identical", SHA_A: "identical"}}


def run(issue: dict | None, prs: list[dict] | None, *, repo: str = PIDEV, live: dict | None = None,
        first_seen: float | None = None, now: datetime = NOW) -> tuple[dict, list[dict]]:
    return ds.classify(issue, prs, live if live is not None else {"revision": None, "compare": {}}, now,
                       repo=repo, project_id="proj", first_seen=first_seen)


def codes(found: list[dict]) -> list[str]:
    return [f["code"] for f in found]


@pytest.fixture(autouse=True)
def _no_reviewers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAO_DELIVERY_HUMAN_REVIEWERS", raising=False)


# ── E1: completed is not Done by itself ───────────────────────────────────────────────────────────
def test_e1_completed_issue_rows() -> None:
    record, _ = run(mission(state="completed", completed=2), [merged_facts(7)], repo=ATO)
    assert record["stage"] == "merged"
    for state in ("completed", "started"):
        record, found = run(mission(state=state, completed=2 if state == "completed" else None), [])
        assert (record["stage"], record["counted"], found) == ("counted", f"{state}_without_pr", [])
    record, found = run(mission(state="completed", completed=2), [open_facts(7, draft=True)])
    assert record["stage"] == "done" and codes(found) == ["FALSE_DONE"]
    assert (record["since"], record["age_source"]) == (ago(2), "completedAt")


# ── E2: human identity only from the allow-list, never from user.type ───────────────────────────
def _with_reviews(reviews: list[dict]) -> dict:
    return run(mission(), [open_facts(7, check_done=0.5, reviews=reviews)])[0]


@pytest.mark.parametrize("env", [None, "someone-else"])
def test_e2_unlisted_approval_stays_review_wait(monkeypatch: pytest.MonkeyPatch, env: str | None) -> None:
    if env:
        monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", env)
    for kind in ("User", "Bot"):
        approval = {**review(FAKE_REVIEWER, "APPROVED", SHA_A), "type": kind, "user": {"type": kind}}
        record = _with_reviews([approval])
        assert record["stage"] == "review_wait" and record["approval_identity_unverified"] is True
        assert record["reviewed_head_sha"] is None


USER_APPROVAL = {**review(FAKE_REVIEWER, "APPROVED", at=3), "type": "User"}


@pytest.mark.parametrize("reviews, stage", [
    ([USER_APPROVAL, review("other", "CHANGES_REQUESTED", at=2)], "building"),
    ([review(FAKE_REVIEWER, "COMMENTED")], "review_wait"),
    ([USER_APPROVAL, review(FAKE_REVIEWER, "CHANGES_REQUESTED", at=2)], "building"),
    ([review(FAKE_REVIEWER, "CHANGES_REQUESTED", at=3), review(FAKE_REVIEWER, "APPROVED", at=2)], "approval_wait"),
    ([review(FAKE_REVIEWER, "APPROVED"), review(FAKE_REVIEWER, "SUPERSEDED")], "unknown"),
])
def test_e2_verdicts(monkeypatch: pytest.MonkeyPatch, reviews: list[dict], stage: str) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", " Fake-Reviewer-ONE , ")
    record = _with_reviews(reviews)
    assert record["stage"] == stage
    if stage == "unknown":
        assert record["reason"] == "bad_review_state"


def test_e2_listed_login_any_case_reaches_approval_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", "FAKE-REVIEWER-ONE")
    record = _with_reviews([review("Fake-Reviewer-One", "APPROVED", SHA_A, at=0.25)])
    assert record["stage"] == "approval_wait" and record["reviewed_head_sha"] == SHA_A
    assert record["approval_identity_unverified"] is False
    assert (record["since"], record["age_source"]) == (ago(0.25), "review_submitted_at")


# ── Rows 8 to 10: checks red or pending build; no CI evidence at all is UNKNOWN, never healthy ───
@pytest.mark.parametrize("checks, stage, passed, source", [
    ("red", "building", False, "check_completed_at"),
    ("pending", "building", False, "pr_created_at"),
    ("none", "unknown", False, "startedAt"),
    ("status_only", "review_wait", True, "pr_created_at"),
])
def test_checks_state_rows(checks: str, stage: str, passed: bool, source: str) -> None:
    record, _ = run(mission(), [open_facts(7, checks=checks)])
    assert (record["stage"], record["tests_passed"], record["age_source"]) == (stage, passed, source)
    if stage == "unknown":
        assert record["reason"] == "no_ci"


def test_human_reviewers_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ds.human_reviewers() == frozenset()
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", " Fake-Reviewer-One ,,fake-reviewer-two , ")
    assert ds.human_reviewers() == frozenset({"fake-reviewer-one", "fake-reviewer-two"})


# ── E3: a timezone-less timestamp makes one mission UNKNOWN; the others classify; nothing raises ──
def test_e3_naive_timestamp_is_unknown_for_that_mission_only() -> None:
    bad = open_facts(7, check_done=0.5)
    bad["created_at"] = "2026-11-15T10:00:00"
    bad["check_runs"][0]["completed_at"] = "2026-11-15T11:00:00"
    record, found = run(mission("RA-1"), [bad])
    assert record["stage"] == "unknown" and record["reason"] == "bad_timestamp"
    assert codes(found) == ["EVIDENCE_UNKNOWN"]
    good, _ = run(mission("RA-2"), [open_facts(8, check_done=0.5)])
    assert good["stage"] == "review_wait"
    naive_now, found = run(mission(), [open_facts(7)], now=NOW.replace(tzinfo=None))
    assert naive_now["stage"] == "unknown" and "EVIDENCE_UNKNOWN" in codes(found)


# ── E7 / F6: UNKNOWN ages from source time; local first-seen only when no source time exists ─────
@pytest.mark.parametrize("started", [25, 30])
def test_e7_f6_unknown_ages_from_started_at(started: float) -> None:
    record, found = run(mission(started=started), [error_item(7, created=None)], first_seen=NOW.timestamp())
    assert codes(found) == ["EVIDENCE_UNKNOWN", "EVIDENCE_UNKNOWN_24H"]
    late = found[1]
    assert (late["severity"], late["next_owner"]) == ("founder", "founder")
    assert (late["since"], late["age_source"]) == (ago(started), "startedAt")
    assert record["age_source"] == "startedAt"


def test_f6_unknown_falls_back_to_pr_then_local_first_seen() -> None:
    record, found = run(mission(started=None), [error_item(7, created=26)])
    assert record["age_source"] == "pr_created_at" and "EVIDENCE_UNKNOWN_24H" in codes(found)
    first = (NOW.timestamp() - 2 * 3600)
    record, found = run(mission(started=None), [error_item(7, created=None)], first_seen=first)
    assert (record["since"], record["age_source"]) == (ago(2), "local_first_seen")
    assert codes(found) == ["EVIDENCE_UNKNOWN"]
    record, _ = run(mission(started=None), [error_item(7, created=None)])
    assert (record["since"], record["age_source"]) == (ago(0), "local_first_seen")


# ── E8 / F7 / G2: only LIVE_SOURCE decides provability; only the compare sets verified_sha ───────
@pytest.mark.parametrize("status, verified", [("identical", SHA_B), ("ahead", SHA_B), ("behind", None),
                                              ("diverged", None), (None, None)])
def test_e8_pidev_compare(status: str | None, verified: str | None) -> None:
    live = {"revision": SHA_C, "compare": {SHA_B: status}}
    record, found = run(mission(), [merged_facts(7, merged=2)], live=live)
    assert record["stage"] == "merged" and record["live_source_provable"] is True
    assert record["authorised_head_sha"] is None and record["merge_sha"] == SHA_B
    assert (record["deployed_sha"], record["verified_sha"]) == (verified, verified)
    assert codes(found) == (["CHECK_ACCEPTANCE"] if verified else [])


@pytest.mark.parametrize("repo", [SYNTHEX, ATO])
def test_e8_f7_non_provable_repo_ignores_live_and_is_labelled(repo: str) -> None:
    for number in (7, 8):
        record, found = run(mission(f"RA-{number}"), [merged_facts(number, repo=repo, merged=30)], repo=repo,
                            live=CONTAINED)
        assert record["verified_sha"] is None and record["deployed_sha"] is None
        assert record["live_source_provable"] is False and codes(found) == ["LIVE_CANNOT_VERIFY"]
        assert found[0]["severity"] == "info"


def test_e8_repo_findings_halves() -> None:
    rec, found = ds.repo_findings(SYNTHEX, 2, SHA_B.upper())
    assert rec["live_source"] == "live_unconfirmed" and rec["live_unconfirmed"] == SHA_B
    assert codes(found) == ["LIVE_UNCONFIRMED"] and found[0]["severity"] == "info" and SHA_B in found[0]["message"]
    rec, found = ds.repo_findings(SYNTHEX, 2, "not-a-sha")
    assert rec["live_unconfirmed"] is None and found == []
    rec, found = ds.repo_findings(ATO, 4, None)
    assert codes(found) == ["NO_DEPLOY_SOURCE"] and "4" in found[0]["message"] and rec["merged_unverifiable"] == 4
    assert found[0]["next_owner"] == "SPM"
    rec, found = ds.repo_findings(PIDEV, 0, SHA_A)
    assert rec["live_source"] == "provable" and rec["live_unconfirmed"] == SHA_A and found == []


@pytest.mark.parametrize("hours, code", [(30, "DEPLOY_UNVERIFIED_24H"), (5, "DEPLOY_UNVERIFIED")])
def test_g2_pidev_with_unreadable_revision_still_ages(hours: float, code: str) -> None:
    record, found = run(mission(), [merged_facts(7, merged=hours)], live={"revision": None, "compare": None})
    assert codes(found) == [code] and record["live_source_provable"] is True
    assert (record["since"], record["age_source"]) == (ago(hours), "merged_at")


def test_g3_live_source_change_upgrades_on_next_call(monkeypatch: pytest.MonkeyPatch) -> None:
    args = (mission(), [merged_facts(7, repo=ATO, merged=30)])
    _, first = run(*args, repo=ATO)
    assert codes(first) == ["LIVE_CANNOT_VERIFY"]
    monkeypatch.setitem(ds.LIVE_SOURCE, "cleanexpo/ato", "provable")
    record, second = run(*args, repo=ATO)
    assert codes(second) == ["DEPLOY_UNVERIFIED_24H"] and record["live_source_provable"] is True


def test_g5_live_source_matches_the_real_registry() -> None:
    allowed = delivery_collect.load_registry().allowed
    assert set(ds.LIVE_SOURCE) == set(allowed) and len(allowed) == 12
    kinds = list(ds.LIVE_SOURCE.values())
    assert [r for r, k in ds.LIVE_SOURCE.items() if k == "provable"] == ["cleanexpo/pi-dev-ops"]
    assert {r for r, k in ds.LIVE_SOURCE.items() if k == "live_unconfirmed"} == {
        "cleanexpo/restoreassist", "cleanexpo/synthex", "cleanexpo/unite-group"}
    assert kinds.count("none") == 8 and "cleanexpo/ccw-crm" not in ds.LIVE_SOURCE
    assert ds.live_kind("CleanExpo/PI-DEV-OPS") == "provable" and ds.live_kind("Fake/Repo") == "none"


# ── E9: nothing sets authorised_head_sha ─────────────────────────────────────────────────────────
def test_e9_authorised_head_sha_is_always_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    approved = open_facts(7, check_done=0.5, reviews=[review(FAKE_REVIEWER, "APPROVED", SHA_A)])
    for prs in ([approved], [merged_facts(7)]):
        record, _ = run(mission(), prs, live=CONTAINED)
        assert record["authorised_head_sha"] is None and record["acceptance_passed"] is False


# ── F4: unowned work at 72 h raises UNOWNED and UNOWNED_24H (founder) ────────────────────────────
def test_f4_unowned_issue_and_orphan_reach_the_founder() -> None:
    issue_rec, issue_found = run(mission(owner=None, started=72), [open_facts(7, check_done=72)])
    orphan_rec, orphan_found = run(None, [orphan_item(9, created=72)])
    for found, since, source in ((issue_found, ago(72), "startedAt"), (orphan_found, ago(72), "pr_created_at")):
        assert codes(found) == ["UNOWNED", "UNOWNED_24H"]
        late = found[1]
        assert (late["severity"], late["next_owner"], late["since"], late["age_source"]) == (
            "founder", "founder", since, source)
    assert issue_rec["owner"] is None and orphan_rec["owner"] is None
    _, done = run(mission(owner=None, state="completed", completed=72), [open_facts(7)])
    assert codes(done) == ["FALSE_DONE"]


# ── F5: several PRs, closed PRs, drafts and bots ─────────────────────────────────────────────────
@pytest.mark.parametrize("prs, stage, extra", [
    ([closed_facts(8)], "counted", "closed_unmerged"),
    ([closed_facts(8), open_facts(7, check_done=0.5)], "review_wait", None),
    ([merged_facts(6), open_facts(7)], "unknown", "multiple_prs"),
    ([open_facts(7), open_facts(8)], "unknown", "multiple_prs"),
    ([open_facts(7, draft=True, created=3)], "building", None),
])
def test_f5_pr_sets(prs: list[dict], stage: str, extra: str | None) -> None:
    record, found = run(mission(), prs)
    assert record["stage"] == stage
    if stage == "counted":
        assert (record["counted"], found) == (extra, [])
    elif stage == "unknown":
        assert record["reason"] == extra
    elif stage == "building":
        assert (record["since"], record["age_source"]) == (ago(3), "pr_created_at")


def test_f5_two_merged_one_not_contained_is_not_live() -> None:
    prs = [merged_facts(6, merge=SHA_A, merged=10, head=SHA_C), merged_facts(7, merge=SHA_B, merged=3)]
    record, _ = run(mission(), prs, live={"revision": SHA_C, "compare": {SHA_B: "identical", SHA_A: "behind"}})
    assert record["merge_sha"] == SHA_B and record["pr_head_sha"] == SHA_A
    assert record["verified_sha"] is None and (record["since"], record["age_source"]) == (ago(3), "merged_at")
    record, found = run(mission(), prs, live=CONTAINED)
    assert record["verified_sha"] == SHA_B and codes(found) == ["CHECK_ACCEPTANCE"]


def test_f5_bot_orphan_is_counted_not_raised() -> None:
    record, found = run(None, [orphan_item(9, author_type="Bot")])
    assert (record["stage"], record["counted"], found) == ("counted", "bot_prs", [])
