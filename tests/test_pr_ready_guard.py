"""Decision tests for the PR ready guard (.github/scripts/pr_ready_guard.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import pr_ready_guard as g  # noqa: E402

GREEN = [g.Check("CI", "success"), g.Check("lint", "success")]


def pr(draft=False, labels=(), mergeable="MERGEABLE", checks=GREEN, **extra):
    return g.PR(1, draft, set(labels), mergeable, list(checks), "a" * 40, "node", **extra)


def test_ready_and_red_goes_to_draft_naming_the_check():
    d = g.decide(pr(checks=[g.Check("CI", "failure"), g.Check("lint", "success")]))
    assert d.action == "draft" and any("CI" in r for r in d.reasons)


def test_ready_and_pending_goes_to_draft():
    d = g.decide(pr(checks=[g.Check("CI", "pending")]))
    assert d.action == "draft" and any("still running: CI" in r for r in d.reasons)


def test_ready_and_conflicting_goes_to_draft():
    d = g.decide(pr(mergeable="CONFLICTING"))
    assert d.action == "draft" and any("conflict" in r for r in d.reasons)


def test_ready_and_green_is_left_alone():
    assert g.decide(pr()).action == "leave"


def test_held_draft_and_green_goes_ready():
    assert g.decide(pr(draft=True, labels=[g.LABEL])).action == "ready"


def test_held_draft_still_red_stays_draft():
    d = g.decide(pr(draft=True, labels=[g.LABEL], checks=[g.Check("CI", "failure")]))
    assert d.action == "leave"


def test_held_draft_with_unknown_mergeability_waits():
    assert g.decide(pr(draft=True, labels=[g.LABEL], mergeable="UNKNOWN")).action == "leave"


def test_unlabelled_draft_is_never_touched_even_when_green():
    assert g.decide(pr(draft=True)).action == "leave"


def test_unlabelled_draft_is_never_touched_even_when_red():
    assert g.decide(pr(draft=True, checks=[g.Check("CI", "failure")])).action == "leave"


def test_guards_own_check_is_ignored_when_pending():
    own = g.Check("pr-ready-guard", "pending")
    assert g.decide(pr(checks=GREEN + [own])).action == "leave"
    assert g.decide(pr(draft=True, labels=[g.LABEL], checks=GREEN + [own])).action == "ready"


def test_guards_own_check_is_ignored_when_failed():
    assert g.decide(pr(checks=GREEN + [g.Check("pr-ready-guard", "failure")])).action == "leave"


def test_held_draft_with_only_its_own_check_waits():
    own = [g.Check("pr-ready-guard", "success")]
    assert g.decide(pr(draft=True, labels=[g.LABEL], checks=own)).action == "leave"


def test_classify_maps_github_states():
    def run(s, c):
        return g.classify({"__typename": "CheckRun", "name": "x", "status": s, "conclusion": c}).state

    assert run("IN_PROGRESS", None) == "pending"
    assert run("COMPLETED", "SUCCESS") == "success"
    assert run("COMPLETED", "SKIPPED") == "success"
    assert run("COMPLETED", "CANCELLED") == "failure"

    def ctx(s):
        return g.classify({"__typename": "StatusContext", "context": "x", "state": s}).state

    assert (ctx("SUCCESS"), ctx("PENDING"), ctx("ERROR")) == ("success", "pending", "failure")


# ---- review threads and merge-blocked state (lead requirement, PR 969 case) ----

def test_green_but_one_unresolved_thread_and_merge_blocked_goes_to_draft():
    d = g.decide(pr(unresolved=1, merge_state="BLOCKED", review_decision="APPROVED"))
    assert d.action == "draft" and any("unresolved review thread" in r for r in d.reasons)


def test_unresolved_thread_on_repo_that_does_not_require_resolution_is_left_alone():
    assert g.decide(pr(unresolved=1, merge_state="CLEAN")).action == "leave"


def test_blocked_only_by_missing_approval_is_left_alone():
    assert g.decide(pr(merge_state="BLOCKED", review_decision="REVIEW_REQUIRED")).action == "leave"


def test_blocked_for_a_reason_other_than_approval_goes_to_draft():
    d = g.decide(pr(merge_state="BLOCKED", review_decision="APPROVED"))
    assert d.action == "draft" and any("BLOCKED" in r for r in d.reasons)


def test_held_draft_green_but_unresolved_thread_is_not_released():
    d = g.decide(pr(draft=True, labels=[g.LABEL], unresolved=2, merge_state="DRAFT"))
    assert d.action == "leave" and any("unresolved" in r for r in d.reasons)


def test_held_draft_green_with_zero_threads_is_released():
    assert g.decide(pr(draft=True, labels=[g.LABEL], merge_state="DRAFT")).action == "ready"


def test_unlabelled_draft_with_unresolved_threads_is_untouched():
    assert g.decide(pr(draft=True, unresolved=3, merge_state="DRAFT")).action == "leave"
