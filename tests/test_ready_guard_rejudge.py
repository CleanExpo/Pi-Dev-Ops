"""The PR ready guard's own red check must not dead-end a PR that later goes green.

Observed 08/11/2026 on #1000 and #1001: the founder readied a PR while its checks were still
running. The ready_for_review run tried to draft it, GitHub refused (RA-8212), and the run
failed on purpose: that red pr-ready-guard check is the hold. But nothing ever re-judged it,
so once the other checks passed the PR stayed BLOCKED until a human re-ran the run by hand.
A later sweep that finds the PR green now re-runs that failed run; a PR whose checks fail
stays held.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import pr_ready_guard as g  # noqa: E402
import ready_guard_rejudge as rj  # noqa: E402

SHA = "c" * 40
FORBIDDEN = [{"type": "FORBIDDEN", "path": ["convertPullRequestToDraft"],
              "message": "Resource not accessible by integration"}]


def _ready(ci="success", own="failure", merge_state="BLOCKED", mergeable="MERGEABLE", unresolved=0, checks=None):
    if checks is None:
        checks = [g.Check("CI", ci), g.Check("pr-ready-guard", own)]
    return g.PR(7, False, set(), mergeable, checks, SHA, "n7", unresolved, merge_state, "")


def _sweep(monkeypatch, tmp_path, prs, trigger=None, refuse=False):
    """Drive run() with GitHub stubbed out; return (exit code, drafted numbers, reruns)."""
    if trigger is None:
        monkeypatch.setenv("GITHUB_EVENT_NAME", "check_suite")
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    else:
        ev = tmp_path / "event.json"
        ev.write_text(json.dumps({"pull_request": {"number": trigger}}))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    drafted, reruns = [], []

    def to_draft(token, repo, p, d):
        if refuse:
            raise g.GraphQLError(FORBIDDEN)
        drafted.append(p.number)

    monkeypatch.setattr(g, "get_token", lambda: "t")
    monkeypatch.setattr(g, "fetch_prs", lambda token, repo: prs)
    monkeypatch.setattr(g, "to_draft", to_draft)
    monkeypatch.setattr(g, "to_ready", lambda *a: None)
    monkeypatch.setattr(g, "upsert_comment", lambda *a: None)
    monkeypatch.setattr(g, "rerun_stale_guard_run", lambda call, token, repo, n, sha: reruns.append((n, sha)))
    return g.run("o/r", False), drafted, reruns


def test_early_readied_pr_is_rejudged_once_its_checks_pass(monkeypatch, tmp_path):
    # 1. Readied while CI runs: drafting refused on the triggering PR, the run fails (the hold).
    rc, _, reruns = _sweep(monkeypatch, tmp_path, [_ready(ci="pending", own="pending")], trigger=7, refuse=True)
    assert rc == 1 and reruns == []
    # 2. CI passes; a sweep sees the PR green, blocked only by the guard's own red check.
    rc, drafted, reruns = _sweep(monkeypatch, tmp_path, [_ready()], refuse=True)
    assert rc == 0 and drafted == [] and reruns == [(7, SHA)]


def test_the_rerun_itself_passes_while_its_own_check_is_running(monkeypatch, tmp_path):
    rc, drafted, reruns = _sweep(monkeypatch, tmp_path, [_ready(own="pending")], trigger=7, refuse=True)
    assert rc == 0 and drafted == [] and reruns == []


def test_pr_with_a_failing_check_stays_held_and_is_never_rerun(monkeypatch, tmp_path):
    rc, _, reruns = _sweep(monkeypatch, tmp_path, [_ready(ci="failure")], refuse=True)
    assert rc == 0 and reruns == []  # sweep: refusal on another PR only warns, nothing re-run
    rc, _, reruns = _sweep(monkeypatch, tmp_path, [_ready(ci="failure")], trigger=7, refuse=True)
    assert rc == 1 and reruns == []  # its own run stays red
    _, drafted, reruns = _sweep(monkeypatch, tmp_path, [_ready(ci="failure")])
    assert drafted == [7] and reruns == []  # where drafting is allowed, it is drafted


def test_not_yet_green_prs_are_not_rerun(monkeypatch, tmp_path):
    for p in (_ready(ci="pending"), _ready(mergeable="UNKNOWN", merge_state="UNKNOWN"),
              _ready(mergeable="CONFLICTING"), _ready(unresolved=1),
              _ready(checks=[g.Check("pr-ready-guard", "failure")])):
        _, _, reruns = _sweep(monkeypatch, tmp_path, [p], refuse=True)
        assert reruns == [], p


def test_green_pr_with_a_green_guard_check_is_left_alone(monkeypatch, tmp_path):
    rc, drafted, reruns = _sweep(monkeypatch, tmp_path, [_ready(own="success", merge_state="CLEAN")])
    assert rc == 0 and drafted == [] and reruns == []


def test_blocked_for_another_reason_with_a_green_guard_check_still_drafts():
    assert g.decide(_ready(own="success")).action == "draft"


# ---- which run gets re-run ----

def _runs(*runs):
    calls = []

    def call(token, method, url, body=None):
        calls.append((method, url))
        return {"workflow_runs": list(runs)} if method == "GET" else {}
    return call, calls


def _run(i, status="completed", conclusion="failure", attempt=1):
    return {"id": i, "status": status, "conclusion": conclusion, "run_attempt": attempt}


def _posted(*runs):
    call, calls = _runs(*runs)
    rj.rerun_stale_guard_run(call, "t", "o/r", 7, SHA)
    get = calls[0][1]
    assert "/actions/workflows/pr-ready-guard.yml/runs?" in get and "head_sha=" + SHA in get
    assert "event=pull_request" in get
    return [u for m, u in calls if m == "POST"]


def test_newest_failed_or_cancelled_run_is_rerun():
    assert _posted(_run(1, conclusion="success"), _run(5)) == [rj.API + "/repos/o/r/actions/runs/5/rerun"]
    assert _posted(_run(6, conclusion="cancelled")) == [rj.API + "/repos/o/r/actions/runs/6/rerun"]


def test_nothing_is_rerun_when_the_newest_run_is_green_or_still_going():
    assert _posted(_run(5), _run(6, conclusion="success")) == []
    assert _posted(_run(5), _run(6, status="in_progress", conclusion=None)) == []
    assert _posted() == []


def test_rerun_stops_after_the_attempt_cap(capsys):
    assert _posted(_run(5, attempt=rj.MAX_ATTEMPTS)) == []
    assert "::warning::" in capsys.readouterr().out


def test_a_rerun_cancelled_by_the_concurrency_group_does_not_use_up_the_cap():
    run = _run(5, conclusion="cancelled", attempt=rj.MAX_ATTEMPTS + 2)
    assert _posted(run) == [rj.API + "/repos/o/r/actions/runs/5/rerun"]


def test_a_refused_rerun_warns_instead_of_failing_the_sweep(capsys):
    import urllib.error

    def call(token, method, url, body=None):
        if method == "POST":
            raise urllib.error.HTTPError(url, 403, "Resource not accessible by integration", None, None)
        return {"workflow_runs": [_run(5)]}
    assert rj.rerun_stale_guard_run(call, "t", "o/r", 7, SHA) is False
    assert "::warning::" in capsys.readouterr().out
