"""W1b — one claim rule for every executor, and claims that cannot loop.

Estate audit 30/09/2026, ranks #1 and #5. Each test names the defect it pins:

- the poller read `first: 10` with no pageInfo, so ticket eleven was invisible;
- the mesh took only `mesh:auto`, so approved `pi-dev:autonomous` work never
  reached a logged-in runner, and swarm intake read a label that does not exist;
- ATO and DR-NRPG Contractor Go-Live had no registry row, so every executor
  dropped their tickets;
- GO on an idea recorded GO and filed nothing;
- a ticket with an open blocker, a fresh Blocked transition, or two starts that
  day was claimed again (RA-7785: 14 times in a day);
- a failed start went back to Ready, and no terminal status released the claim;
- nothing capped what one ticket could spend across retries.

No live Linear, Supabase or claude call: every boundary is faked.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.server import autonomy, session_lease, supabase_log
from app.server import autonomy_eligibility as elig

from w1b_helpers import _NOW, _PROJECT, _START, REPO_ROOT, _ago, _issue  # noqa: E402


# ── claim_refusal: the loop guards ───────────────────────────────────────────

@pytest.mark.parametrize(("issue", "reason"), [
    (_issue(), None),
    (_issue(blockers=[("RA-7474", "started")]), "blocked-by"),
    (_issue(blockers=[("RA-7474", "completed")]), None),
    (_issue(blockers=[("RA-7474", "canceled")]), None),
    (_issue(history=[("Pi-Dev: Blocked", _ago(3))]), "recently-blocked"),
    (_issue(history=[("Pi-Dev: Blocked", _ago(30))]), None),
    (_issue(comments=[(_START, _ago(1)), (_START, _ago(5))]), "repeat-claim"),
    (_issue(comments=[(_START, _ago(1)), (_START, _ago(40))]), None),
    (_issue(labels=("pi-dev:autonomous", "pi-dev:blocked-reason:session-lost")), "blocked-reason"),
], ids=["clean", "open-blocker", "done-blocker", "canceled-blocker", "blocked-3h",
        "blocked-30h", "two-starts-24h", "one-start-24h", "blocked-reason-label"])
def test_claim_refusal(issue, reason):
    assert elig.claim_refusal(issue, _NOW) == reason
    assert elig.issue_is_claimable(issue, registered_project_ids={_PROJECT}, now=_NOW) is (reason is None)


def test_mesh_states_admit_todo_but_poller_does_not():
    todo = _issue(state="Todo")
    assert not elig.issue_is_claimable(todo, registered_project_ids={_PROJECT})
    assert elig.issue_is_claimable(todo, registered_project_ids={_PROJECT}, states=elig.MESH_STATES)


# ── Registry ────────────────────────────────────────────────────────────────

def test_ato_and_dr_nrpg_go_live_are_registered():
    repos = elig.registry_repos(REPO_ROOT / "config/harness/projects.json")
    assert repos["20bb0ca6-0176-46c4-be4c-cd34ac89767d"] == "CleanExpo/ATO"
    assert repos["ba150052-ff1c-4750-a0bc-7a8261d4d72b"] == "CleanExpo/DR-NRPG"
    ids = [p["id"] for p in json.loads((REPO_ROOT / "config/harness/projects.json").read_text())["projects"]]
    assert ids.index("dr-nrpg") < ids.index("dr-nrpg-go-live"), "first-match repo lookup must stay dr-nrpg"


# ── Poller: pagination and refusals ─────────────────────────────────────────

_ROW = {"project_id": _PROJECT, "team_id": "team-a", "repo_url": "https://github.com/x/y", "name": "A"}


def _paged_gql(pages: list[list[dict]], seen: list):
    def fake(_key, query, variables=None):
        seen.append((query, dict(variables or {})))
        if variables.get("autonomyLabel") != "pi-dev:autonomous":
            return {"project": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}
        idx = int(variables.get("after") or 0)
        more = idx + 1 < len(pages)
        return {"project": {"issues": {"nodes": pages[idx], "pageInfo": {
            "hasNextPage": more, "endCursor": str(idx + 1) if more else None}}}}
    return fake


def test_fetch_reads_every_page():
    pages = [[_issue(f"RA-{i}") for i in range(p * 50, p * 50 + 50)] for p in range(2)] + [[_issue("RA-100")]]
    seen: list = []
    with patch.object(autonomy, "_load_portfolio_projects", return_value=[_ROW]), \
         patch.object(autonomy, "_gql", side_effect=_paged_gql(pages, seen)), \
         patch.object(autonomy, "_PRIORITY_FILTER", set()):
        got = autonomy.fetch_todo_issues("k")
    assert len(got) == 101
    assert "pageInfo" in seen[0][0] and "after" in seen[0][0]


def test_fetch_drops_guarded_and_reports_repeat_claims():
    now_start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    repeat = _issue("RA-REP", comments=[(_START, now_start), (_START, now_start)])
    blocked = _issue("RA-BLK", blockers=[("RA-9", "started")])
    refused: list = []
    with patch.object(autonomy, "_load_portfolio_projects", return_value=[_ROW]), \
         patch.object(autonomy, "_gql", side_effect=_paged_gql([[_issue("RA-OK"), repeat, blocked]], [])), \
         patch.object(autonomy, "_PRIORITY_FILTER", set()):
        got = autonomy.fetch_todo_issues("k", refused=refused)
    assert [i["identifier"] for i in got] == ["RA-OK"]
    assert [i["identifier"] for i in refused] == ["RA-REP"]


def test_repeat_claim_is_labelled_and_parked():
    calls: list = []
    with patch.object(autonomy, "add_label_to_issue", side_effect=lambda *a: calls.append(("label", a[3]))), \
         patch.object(autonomy, "transition_issue", side_effect=lambda *a, **k: calls.append(("state", a[2]))), \
         patch.object(autonomy, "comment_on_issue", side_effect=lambda *a: calls.append(("comment",))), \
         patch.object(autonomy, "_log_event"):
        from app.server import autonomy_queue
        autonomy_queue.block_repeat_claims("k", [{"id": "u", "identifier": "RA-REP", "_team_id": autonomy._RA_TEAM_ID}])
    assert ("label", "pi-dev:blocked-reason:repeat-claim") in calls
    assert ("state", "Pi-Dev: Blocked") in calls


# ── Start failure: Blocked, never Ready; claim released ──────────────────────

def test_failed_start_parks_blocked_and_releases_claim(monkeypatch):
    states: list = []
    released: list = []

    async def boom(**_kw):
        raise RuntimeError("capacity")

    cfg = SimpleNamespace(LINEAR_API_KEY="k")
    monkeypatch.setattr(autonomy, "transition_issue", lambda _k, _i, s, team_id=None: states.append(s))
    monkeypatch.setattr(autonomy, "comment_on_issue", lambda *a: None)
    monkeypatch.setattr(autonomy, "add_label_to_issue", lambda *a: True)
    monkeypatch.setattr(autonomy, "_log_event", lambda *_: None)
    monkeypatch.setattr(autonomy, "generation_blocked", lambda *_: False)
    monkeypatch.setattr(session_lease, "claim_linear_ticket", lambda _i: True)
    monkeypatch.setattr(session_lease, "release_linear_ticket", lambda i, s="released": released.append((i, s)))
    monkeypatch.setenv("TAO_TICKET_TOKEN_CAP", "0")
    issue = {**_issue("RA-7785"), "_team_id": autonomy._RA_TEAM_ID, "description": "fix the thing"}
    asyncio.run(autonomy._process_autonomy_issue(cfg, boom, issue))
    assert "Ready for Pi-Dev" not in states
    assert states[-1] == "Pi-Dev: Blocked"
    assert released == [("RA-7785", "failed")]


def test_release_ends_only_the_claim_row_this_process_inserted(monkeypatch):
    sent: list = []
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x", "key"))
    monkeypatch.setattr(session_lease, "claim_machine", lambda: "railway")
    monkeypatch.setattr(supabase_log, "_upsert", lambda *a: True)
    monkeypatch.setattr(supabase_log, "_insert", lambda t, row: sent.append(("POST", row)) or True)
    monkeypatch.setattr(supabase_log, "_request", lambda m, p, b=None, pr="": sent.append((m, p, b)) or (204, None))
    # Another replica (same machine name) never inserted RA-1 here: nothing to release.
    assert session_lease.release_linear_ticket("RA-1", "done") is False and sent == []
    assert session_lease.claim_linear_ticket("RA-1") is True
    claim_id = sent[0][1]["id"]
    assert session_lease.release_linear_ticket("RA-1", "done") is True
    method, path, body = sent[-1]
    assert method == "PATCH" and f"id=eq.{claim_id}" in path and "machine=" not in path
    assert "state=in.(claimed,working)" in path and body["state"] == "done"
    assert session_lease.release_linear_ticket("RA-1", "done") is False  # released once


def test_failed_release_keeps_the_claim_id_for_a_retry(monkeypatch):
    status = iter([0, 204])
    patches: list = []
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x", "key"))
    monkeypatch.setattr(session_lease, "_OWN_CLAIMS", {"RA-2": "claim-2"})
    monkeypatch.setattr(supabase_log, "_request", lambda m, p, b=None, pr="": patches.append(p) or (next(status), None))
    assert session_lease.release_linear_ticket("RA-2", "failed") is False
    assert session_lease.release_linear_ticket("RA-2", "failed") is True
    assert len(patches) == 2 and all("id=eq.claim-2" in p for p in patches)


def _terminal(monkeypatch, label_ok: bool):
    from app.server import session_linear
    calls: list = []
    monkeypatch.setattr(session_lease, "release_linear_ticket", lambda i, s="released": calls.append(("release", i, s)))
    monkeypatch.setattr(autonomy, "add_label_to_issue", lambda *a: calls.append(("label", a[3])) or label_ok)
    monkeypatch.setattr(autonomy, "_gql", lambda *_a, **_k: {"issue": {"identifier": "RA-5", "team": {"id": "t"}}})
    monkeypatch.setattr(session_linear, "_send_autonomy_outcome_telegram", lambda _s: None)
    monkeypatch.setattr(session_linear, "_post_linear_comment", lambda *_a: None)
    monkeypatch.setattr(session_linear, "_update_linear_state", lambda *_a: None)
    s = SimpleNamespace(id="s1", status="failed", started_at=None, evaluator_score=None,
                        evaluator_status="", linear_issue_id="uuid-5", autonomy_triggered=True)
    session_linear._sync_linear_on_completion(s)
    return calls


def test_failed_session_is_labelled_unclaimable_before_its_claim_is_released(monkeypatch):
    assert _terminal(monkeypatch, True) == [
        ("label", "pi-dev:blocked-reason:session-failed"), ("release", "RA-5", "failed")]


def test_failed_session_that_cannot_be_labelled_keeps_its_claim(monkeypatch):
    assert _terminal(monkeypatch, False) == [("label", "pi-dev:blocked-reason:session-failed")]


def test_park_never_moves_an_unlabelled_ticket_into_a_claimable_state(monkeypatch):
    from app.server import autonomy_queue
    states: list = []
    monkeypatch.setattr(autonomy, "add_label_to_issue", lambda *a: False)
    monkeypatch.setattr(autonomy, "transition_issue", lambda *a, **k: states.append(a[2]))
    monkeypatch.setattr(autonomy, "comment_on_issue", lambda *a: None)
    # UNI's recovery state is Todo, which the mesh lane reads.
    assert autonomy_queue._park("k", "u", autonomy._UNI_TEAM_ID, "pi-dev:blocked-reason:x", "c") == "unchanged"
    assert states == []


# ── Token cap across retries ────────────────────────────────────────────────

def test_ticket_over_cumulative_token_cap_is_not_claimed(monkeypatch):
    from app.server import autonomy_queue
    claimed: list = []
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x", "key"))
    monkeypatch.setattr(supabase_log, "_request",
                        lambda *a, **k: (200, [{"used": 120_000}, {"used": 200_000}]))
    monkeypatch.setattr(session_lease, "claim_linear_ticket", lambda i: claimed.append(i) or True)
    monkeypatch.setattr(autonomy, "transition_issue", lambda *a, **k: None)
    monkeypatch.setattr(autonomy, "comment_on_issue", lambda *a: None)
    labels: list = []
    monkeypatch.setattr(autonomy, "add_label_to_issue", lambda *a: labels.append(a[3]))
    monkeypatch.setattr(autonomy, "_log_event", lambda *_: None)
    monkeypatch.delenv("TAO_TICKET_TOKEN_CAP", raising=False)
    monkeypatch.setattr(autonomy, "generation_blocked", lambda *_: False)
    cfg = SimpleNamespace(LINEAR_API_KEY="k")
    issue = {**_issue("RA-1"), "_team_id": autonomy._RA_TEAM_ID, "description": "fix the thing"}

    async def never(**_kw):
        raise AssertionError("a capped ticket must not start a session")

    asyncio.run(autonomy._process_autonomy_issue(cfg, never, issue))
    assert claimed == [] and labels == [autonomy_queue.TOKEN_CAP_LABEL]


def test_unreadable_token_ledger_refuses_rather_than_guessing(monkeypatch):
    from app.server import autonomy_queue
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("", ""))
    assert autonomy_queue.tokens_spent("uuid-1") is None  # no ledger is unknown, not zero
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x", "key"))
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: (200, [{"used": None}, {"used": 5}]))
    assert autonomy_queue.tokens_spent("uuid-1") == 100_005  # a row without spend is charged, not zeroed
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **k: (0, None))
    assert autonomy_queue.tokens_spent("uuid-1") is None
    assert autonomy_queue.token_cap_refusal(SimpleNamespace(LINEAR_API_KEY="k"), "uuid-1", "RA-1", "t") is True
