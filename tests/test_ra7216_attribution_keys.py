"""
test_ra7216_attribution_keys.py — RA-7216 gap 2, step 2 (attribution keys).

Design: docs/DESIGN-RA-7216-rollback-telemetry-2026-08-14.md §6, §10 step 2.

These keys are what a future revert detector matches against. A revert commit
names the SHA it reverts; before this, no gate_checks row held a SHA, PR number
or branch, so a revert had nothing to attach to. No detector is implemented here
— keys must accrue first, because a revert can only match rows that already
carry a merge_sha.

Covers:
  - parse_github_event surfaces merge identity on pull_request events
  - a close WITHOUT merge is not treated as a merge
  - log_gate_check carries the ship-time keys (repo_name, pr_number, head_branch)
  - record_merge matches on (repo_name, pr_number) and only unstamped rows
  - the merged-PR webhook branch records instead of triggering a build
  - ordering: it runs BEFORE the RA-1182 self-modification skip

All Supabase HTTP is mocked. No live network in CI.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch


# ── parse_github_event: the merge identity ────────────────────────────────────

def _pr_payload(action="closed", merged=True, sha="abc123def4567890",
                number=7, repo="CleanExpo/Pi-Dev-Ops", merged_at="2026-08-14T04:00:00Z"):
    return {
        "repository": {"html_url": f"https://github.com/{repo}", "full_name": repo},
        "action": action,
        "pull_request": {
            "head": {"ref": "pidev/auto-1234abcd"},
            "merged": merged,
            "number": number,
            "merge_commit_sha": sha,
            "merged_at": merged_at,
        },
    }


def test_merged_pr_surfaces_merge_identity():
    """MUTATION CONTROL: drop the merge_commit_sha/merged fields → this fails."""
    from app.server.webhook import parse_github_event

    e = parse_github_event("pull_request", _pr_payload())
    assert e["merged"] is True
    assert e["pr_number"] == 7
    assert e["merge_commit_sha"] == "abc123def4567890"
    assert e["repo_name"] == "CleanExpo/Pi-Dev-Ops"
    assert e["merged_at"] == "2026-08-14T04:00:00Z"


def test_abandoned_close_is_not_a_merge():
    """GitHub sends action=closed for abandoned PRs too, and populates
    merge_commit_sha on them. The `merged` flag is what separates the two —
    presence of a SHA does not."""
    from app.server.webhook import parse_github_event

    e = parse_github_event("pull_request", _pr_payload(merged=False))
    assert e["merged"] is False


def test_push_events_are_unaffected():
    """NEGATIVE CONTROL: the push path must not change shape."""
    from app.server.webhook import parse_github_event

    e = parse_github_event("push", {
        "repository": {"html_url": "https://github.com/CleanExpo/Pi-Dev-Ops"},
        "ref": "refs/heads/main",
    })
    assert e["ref"] == "refs/heads/main"
    assert e["event"] == "push"


# ── ship-time keys ────────────────────────────────────────────────────────────

def test_log_gate_check_carries_ship_time_keys():
    """MUTATION CONTROL: drop the repo_name/pr_number/head_branch passthrough."""
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_insert",
                      side_effect=lambda t, r: captured.update(row=r) or True):
        supabase_log.log_gate_check(
            pipeline_id="p1", session_id="s1", gate_checks={"spec_exists": True},
            review_score=8.0, shipped=True,
            repo_name="CleanExpo/Pi-Dev-Ops", pr_number=7,
            head_branch="pidev/auto-1234abcd",
        )
    assert captured["row"]["repo_name"] == "CleanExpo/Pi-Dev-Ops"
    assert captured["row"]["pr_number"] == 7
    assert captured["row"]["head_branch"] == "pidev/auto-1234abcd"


def test_ship_time_keys_omitted_when_no_pr_was_opened():
    """A session that opened no PR must not write an empty key — an empty
    pr_number would make the row matchable by a merge it has nothing to do
    with."""
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_insert",
                      side_effect=lambda t, r: captured.update(row=r) or True):
        supabase_log.log_gate_check(
            pipeline_id="p1", session_id="s1", gate_checks={"spec_exists": True},
            review_score=8.0, shipped=False,
        )
    for key in ("repo_name", "pr_number", "head_branch"):
        assert key not in captured["row"]


def test_ship_gate_check_call_site_passes_attribution_keys():
    """MUTATION CONTROL: the caller, not just the helper.

    The equivalent slice-2 test passed while the call site dropped its key —
    that is why _log_ship_gate_check was extracted. Same trap, same guard.
    """
    from app.server import session_phases

    session = SimpleNamespace(
        id="sid-1", workspace="/nonexistent", evaluator_status="passed",
        evaluator_score=9.0, evaluator_confidence=88.0, scope_adhered=True,
        modified_files=["a.py"], started_at=1700000000.0, linear_issue_id="RA-1",
        repo_name="CleanExpo/Pi-Dev-Ops", pr_number=7,
        head_branch="pidev/auto-1234abcd",
    )
    captured = {}
    with patch.object(session_phases, "log_gate_check",
                      side_effect=lambda **kw: captured.update(kw)):
        session_phases._log_ship_gate_check(session, push_ok=True, push_ts=1700000600.0)

    assert captured["repo_name"] == "CleanExpo/Pi-Dev-Ops"
    assert captured["pr_number"] == 7
    assert captured["head_branch"] == "pidev/auto-1234abcd"


# ── record_merge ──────────────────────────────────────────────────────────────

def test_record_merge_matches_on_repo_and_pr_and_only_unstamped_rows():
    """MUTATION CONTROL: drop repo_name from the filter, or drop
    `merge_sha=is.null`, and this fails.

    pr_number is unique only WITHIN a repo. Pi-CEO ships to a dozen portfolio
    repos, so PR #5 exists in many of them; matching on pr_number alone would
    stamp one repo's merge onto another repo's row.
    """
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_patch",
                      side_effect=lambda t, f, b: captured.update(table=t, filter=f, body=b) or True):
        ok = supabase_log.record_merge(
            repo_name="CleanExpo/Pi-Dev-Ops", pr_number=7,
            merge_sha="abc123def4567890", merged_at="2026-08-14T04:00:00Z",
        )

    assert ok is True
    assert captured["table"] == "gate_checks"
    assert "repo_name=eq.CleanExpo/Pi-Dev-Ops" in captured["filter"]
    assert "pr_number=eq.7" in captured["filter"]
    assert "merge_sha=is.null" in captured["filter"]
    assert captured["body"]["merge_sha"] == "abc123def4567890"
    assert captured["body"]["merged_at"] == "2026-08-14T04:00:00Z"


def test_record_merge_rejects_incomplete_identity():
    """Never PATCH on a partial filter — that would stamp unrelated rows."""
    from app.server import supabase_log

    with patch.object(supabase_log, "_patch") as mock_patch:
        assert supabase_log.record_merge(
            repo_name="", pr_number=7, merge_sha="abc") is False
        assert supabase_log.record_merge(
            repo_name="r", pr_number=0, merge_sha="abc") is False
        assert supabase_log.record_merge(
            repo_name="r", pr_number=7, merge_sha="") is False
    mock_patch.assert_not_called()


def test_record_merge_is_non_fatal():
    from app.server import supabase_log

    with patch.object(supabase_log, "_patch", return_value=False):
        assert supabase_log.record_merge(
            repo_name="r", pr_number=7, merge_sha="abc") is False


# ── the webhook branch: records, does not trigger ─────────────────────────────

def _call_webhook(payload: dict, monkeypatched_record, monkeypatched_create):
    """Drive the webhook route with a signed GitHub pull_request event."""
    from app.server.routes import webhooks as wh

    raw = json.dumps(payload).encode()

    class _Req:
        headers = {"x-github-event": "pull_request", "x-hub-signature-256": "sha256=x"}
        async def body(self): return raw
        client = SimpleNamespace(host="127.0.0.1")

    with patch.object(wh.config, "GITHUB_WEBHOOK_SECRET", "s"), \
         patch.object(wh, "verify_github_signature", return_value=True), \
         patch.object(wh, "record_merge", side_effect=monkeypatched_record), \
         patch.object(wh, "create_session", side_effect=monkeypatched_create):
        # asyncio.run, NOT get_event_loop().run_until_complete(): from Python
        # 3.10 get_event_loop() raises "There is no current event loop" when no
        # loop is running and none has been set, which is the state pytest
        # leaves the main thread in. That is what failed CI on the first push of
        # this PR — a defect in this harness, not in the route.
        return asyncio.run(wh.webhook(_Req()))


def test_merged_pr_records_and_does_not_spawn_a_session():
    """MUTATION CONTROL: remove the merged-PR branch → a merge spawns a build.

    That is the failure mode RA-1182 exists to prevent, in a new form.
    """
    calls = {"merge": 0, "session": 0}

    def _rec(**kw):
        calls["merge"] += 1
        assert kw["repo_name"] == "CleanExpo/Pi-Dev-Ops"
        assert kw["pr_number"] == 7
        assert kw["merge_sha"] == "abc123def4567890"
        return True

    async def _create(*a, **k):
        calls["session"] += 1
        return SimpleNamespace(id="should-not-happen")

    result = _call_webhook(_pr_payload(), _rec, _create)

    assert calls["merge"] == 1
    assert calls["session"] == 0
    assert result["recorded"] is True
    assert result["triggered"] is False
    assert result["event"] == "pull_request_merged"


def test_merge_on_pi_dev_ops_itself_is_still_recorded():
    """MUTATION CONTROL: move the merged-PR branch below the RA-1182
    self-modification skip → this fails.

    That skip exists to stop Pi-CEO BUILDING against its own repo. Recording a
    merge is not building. With the ordering wrong, the repo that ships the most
    changes becomes the one blind spot in rollback attribution — the exact
    mistake the design flagged as the one an obvious implementation makes.
    """
    calls = {"merge": 0, "session": 0}

    def _rec(**kw):
        calls["merge"] += 1
        return True

    async def _create(*a, **k):
        calls["session"] += 1
        return SimpleNamespace(id="x")

    _call_webhook(_pr_payload(repo="CleanExpo/Pi-Dev-Ops"), _rec, _create)

    assert calls["merge"] == 1, "Pi-CEO's own merges must still be attributed"
    assert calls["session"] == 0


def test_merge_branch_precedes_both_skips_in_source_order():
    """Structural guard on the ordering, readable without importing the route.

    The three behavioural tests above import app.server.routes.webhooks, which
    pulls in FastAPI. That is fine in CI but means they cannot run in a bare
    environment — and the ordering they protect is the single most
    consequential property of this change. This asserts the same invariant by
    reading the source, so it holds everywhere.

    Structural tests are usually a poor substitute for behavioural ones. It is
    kept ALONGSIDE them, never instead: if the two ever disagree, the
    behavioural tests are right and this one is stale.
    """
    from pathlib import Path

    src = Path(__file__).parent.parent / "app" / "server" / "routes" / "webhooks.py"
    text = src.read_text(encoding="utf-8")

    merge_branch = text.index('"event": "pull_request_merged"')
    self_mod_skip = text.index("Pi-CEO harness self-modification blocked")
    auto_branch_skip = text.index("Pi-CEO auto-branch")
    create_call = text.index("await create_session(")

    assert merge_branch < self_mod_skip, (
        "merged-PR handling must precede the RA-1182 self-modification skip, "
        "or Pi-CEO's own merges are never attributed"
    )
    assert merge_branch < auto_branch_skip, (
        "merged-PR handling must precede the pidev/ auto-branch skip"
    )
    assert merge_branch < create_call, (
        "merged-PR handling must precede session creation, or a merge spawns a build"
    )


def test_abandoned_pr_close_records_nothing():
    """NEGATIVE CONTROL. Without this, 'record on every closed PR' passes the
    cases above and would attribute merges that never happened."""
    calls = {"merge": 0, "session": 0}

    def _rec(**kw):
        calls["merge"] += 1
        return True

    async def _create(*a, **k):
        calls["session"] += 1
        return SimpleNamespace(id="x")

    _call_webhook(_pr_payload(repo="CleanExpo/RestoreAssist", merged=False), _rec, _create)

    assert calls["merge"] == 0
