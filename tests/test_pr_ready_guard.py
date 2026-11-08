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


def test_ready_and_pending_is_left_alone():
    d = g.decide(pr(checks=[g.Check("CI", "pending")]))
    assert d.action == "leave" and d.reasons == []


def test_ready_pending_plus_completed_failure_still_drafts():
    d = g.decide(pr(checks=[g.Check("CI", "pending"), g.Check("lint", "failure")]))
    assert d.action == "draft" and any("lint" in r for r in d.reasons)
    assert not any("still running" in r for r in d.reasons)


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


def test_held_draft_still_pending_is_not_released():
    d = g.decide(pr(draft=True, labels=[g.LABEL], checks=[g.Check("CI", "pending")]))
    assert d.action == "leave" and any("still running: CI" in r for r in d.reasons)


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


def test_blocked_only_because_checks_are_pending_is_left_alone():
    d = g.decide(pr(checks=[g.Check("CI", "pending")], merge_state="BLOCKED", review_decision="APPROVED"))
    assert d.action == "leave"


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


# ---- Pass/fail of the check: only the triggering PR, and only real failures ----
# Each run sweeps every open PR. Pending checks, a GitHub FORBIDDEN on convert-to-draft,
# and another PR's error must not turn this check red. A completed failing check on the
# triggering PR is still drafted; a non-permission error acting on that PR still fails.

import json  # noqa: E402

FORBIDDEN = [{"type": "FORBIDDEN", "path": ["convertPullRequestToDraft"],
              "message": "Resource not accessible by integration"}]


def _red(number):
    return g.PR(number, False, set(), "MERGEABLE", [g.Check("CI", "failure")], "b" * 40, "n%d" % number)


def _pending(number):
    return g.PR(number, False, set(), "MERGEABLE", [g.Check("CI", "pending")], "c" * 40, "n%d" % number)


def _sweep(monkeypatch, tmp_path, prs, trigger=None, draft_error=None):
    """Drive run() with GitHub stubbed out; return (exit code, PR numbers drafted)."""
    if trigger is None:
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    else:
        ev = tmp_path / "event.json"
        ev.write_text(json.dumps({"pull_request": {"number": trigger}}))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    drafted = []

    def to_draft(token, repo, p, d):
        if draft_error is not None and p.number in draft_error[0]:
            raise draft_error[1]
        drafted.append(p.number)

    monkeypatch.setattr(g, "get_token", lambda: "t")
    monkeypatch.setattr(g, "fetch_prs", lambda token, repo: prs)
    monkeypatch.setattr(g, "to_draft", to_draft)
    monkeypatch.setattr(g, "to_ready", lambda *a: None)
    monkeypatch.setattr(g, "upsert_comment", lambda *a: None)
    return g.run("o/r", False), drafted


def test_pending_checks_pass(monkeypatch, tmp_path):
    rc, drafted = _sweep(monkeypatch, tmp_path, [_pending(995)], trigger=995)
    assert rc == 0 and drafted == []


def test_forbidden_draft_conversion_warns_not_failure(monkeypatch, tmp_path, capsys):
    rc, _ = _sweep(monkeypatch, tmp_path, [_red(981)], trigger=981,
                   draft_error=({981}, g.GraphQLError(FORBIDDEN)))
    assert rc == 0
    assert "::warning::" in capsys.readouterr().out


def test_other_pr_error_does_not_fail_this_pr(monkeypatch, tmp_path, capsys):
    other = g.GraphQLError([{"type": "INTERNAL", "path": ["convertPullRequestToDraft"], "message": "boom"}])
    rc, _ = _sweep(monkeypatch, tmp_path, [_pending(981), _red(970)], trigger=981,
                   draft_error=({970}, other))
    assert rc == 0
    assert "::warning::" in capsys.readouterr().out


def test_real_completed_failure_still_fails(monkeypatch, tmp_path):
    boom = g.GraphQLError([{"type": "INTERNAL", "path": ["convertPullRequestToDraft"], "message": "boom"}])
    rc, drafted = _sweep(monkeypatch, tmp_path, [_red(981)], trigger=981, draft_error=({981}, boom))
    assert rc == 1 and drafted == []
    d = g.decide(_red(981))
    assert d.action == "draft" and any("CI" in r for r in d.reasons)


def test_unrelated_pr_draft_forbidden_warns_and_passes(monkeypatch, tmp_path, capsys):
    rc, _ = _sweep(monkeypatch, tmp_path, [_red(970), _red(979)], trigger=981,
                   draft_error=({970, 979}, g.GraphQLError(FORBIDDEN)))
    assert rc == 0
    assert "::warning::" in capsys.readouterr().out


def test_sweep_without_a_triggering_pr_warns_and_passes_on_forbidden(monkeypatch, tmp_path):
    rc, _ = _sweep(monkeypatch, tmp_path, [_red(970)], draft_error=({970}, g.GraphQLError(FORBIDDEN)))
    assert rc == 0


def test_forbidden_on_a_different_mutation_still_fails(monkeypatch, tmp_path):
    err = g.GraphQLError([{"type": "FORBIDDEN", "path": ["markPullRequestReadyForReview"], "message": "x"}])
    rc, _ = _sweep(monkeypatch, tmp_path, [_red(981)], trigger=981, draft_error=({981}, err))
    assert rc == 1


def test_unrelated_pr_is_drafted_when_permission_exists(monkeypatch, tmp_path):
    rc, drafted = _sweep(monkeypatch, tmp_path, [_red(970), _red(981)], trigger=981)
    assert rc == 0 and drafted == [970, 981]


def test_refusal_mixed_with_another_error_still_fails(monkeypatch, tmp_path):
    mixed = g.GraphQLError(FORBIDDEN + [{"type": "INTERNAL", "path": ["convertPullRequestToDraft"], "message": "x"}])
    rc, _ = _sweep(monkeypatch, tmp_path, [_red(981)], trigger=981, draft_error=({981}, mixed))
    assert rc == 1
