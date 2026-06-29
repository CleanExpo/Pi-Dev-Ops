"""Contract tests for SupabasePendingRoundSource + SupabaseRoundUpdater.

Fake transport serves canned board-round / thread / project / message rows and
records PATCHes, so these assert PendingRound assembly and the round/thread
state transitions without a DB.
"""
import json

from swarm.intake.round_query import SupabasePendingRoundSource, SupabaseRoundUpdater


_BRIEF = {
    "layout": "single-page", "framework": "next", "suitability": "fit",
    "swot": {"strengths": ["s1"], "weaknesses": [], "opportunities": [], "threats": []},
    "open_questions": ["budget?"], "ready_for_production": False, "rationale": "solid",
}


class FakeSb:
    def __init__(self, *, rounds=None, threads=None, projects=None, messages=None):
        self.calls = []
        self._rounds = rounds if rounds is not None else []
        self._threads = threads if threads is not None else []
        self._projects = projects if projects is not None else []
        self._messages = messages if messages is not None else []

    def __call__(self, method, path, params=None, body=None, extra_headers=None):
        self.calls.append({"method": method, "path": path, "params": params or {}, "body": body})
        if method == "GET" and path == "/intake_board_rounds":
            return self._rounds
        if method == "GET" and path == "/intake_threads":
            return self._threads
        if method == "GET" and path == "/intake_projects":
            return self._projects
        if method == "GET" and path == "/intake_messages":
            return self._messages
        return None

    def of(self, method, path):
        return [c for c in self.calls if c["method"] == method and c["path"] == path]


def _project_row():
    return {"id": "proj-1", "workspace_slug": "duncan-ws", "name": "Acme", "slug": "acme",
            "owner_partner_id": "partner_owner", "approval_policy": "creator_only",
            "description": "portal", "status": "in_board", "github_repo": None}


# ── PendingRoundSource ───────────────────────────────────────────────────────
def test_assembles_pending_round_from_joins():
    sb = FakeSb(
        rounds=[{"id": "r-1", "thread_id": "th-1", "board_session_id": "board-1", "spm_brief": _BRIEF}],
        threads=[{"project_id": "proj-1"}],
        projects=[_project_row()],
        messages=[{"submitted_by_partner_id": "partner_duncan"}],
    )
    out = list(SupabasePendingRoundSource(sb_request=sb)())
    assert len(out) == 1
    pr = out[0]
    assert pr.round_id == "r-1" and pr.board_session_id == "board-1"
    assert pr.project.project_id == "proj-1" and pr.project.name == "Acme"
    assert pr.spm_brief.layout == "single-page"
    assert pr.spm_brief.swot.strengths == ["s1"]
    assert pr.requesting_partner_id == "partner_duncan"   # latest inbound message
    # only requested/deliberating rounds queried
    assert sb.of("GET", "/intake_board_rounds")[0]["params"]["status"] == "in.(requested,deliberating)"


def test_requesting_partner_falls_back_to_project_owner():
    sb = FakeSb(
        rounds=[{"id": "r-1", "thread_id": "th-1", "board_session_id": "board-1", "spm_brief": _BRIEF}],
        threads=[{"project_id": "proj-1"}],
        projects=[_project_row()],
        messages=[],  # no inbound message
    )
    pr = list(SupabasePendingRoundSource(sb_request=sb)())[0]
    assert pr.requesting_partner_id == "partner_owner"


def test_round_without_session_or_project_is_skipped():
    sb = FakeSb(
        rounds=[{"id": "r-1", "thread_id": "th-1", "board_session_id": None, "spm_brief": _BRIEF}],
    )
    assert list(SupabasePendingRoundSource(sb_request=sb)()) == []


def test_spm_brief_roundtrips_from_jsonb():
    # asdict(SPMBrief) is what round_store persisted; reconstruct must be faithful.
    sb = FakeSb(
        rounds=[{"id": "r-1", "thread_id": "th-1", "board_session_id": "b", "spm_brief": _BRIEF}],
        threads=[{"project_id": "proj-1"}], projects=[_project_row()], messages=[],
    )
    pr = list(SupabasePendingRoundSource(sb_request=sb)())[0]
    assert json.dumps(_BRIEF)  # sanity: input is json
    assert pr.spm_brief.open_questions == ["budget?"]
    assert pr.spm_brief.ready_for_production is False


# ── RoundUpdater ─────────────────────────────────────────────────────────────
def test_mark_replied_patches_round_and_advances_thread():
    sb = FakeSb(rounds=[{"thread_id": "th-1"}])  # the thread_id lookup for advancing
    SupabaseRoundUpdater(sb_request=sb).mark_replied(
        round_id="r-1", aggregated_reply="here is the board view", next_action="awaiting_partner")
    rpatch = sb.of("PATCH", "/intake_board_rounds")[0]
    assert rpatch["params"]["id"] == "eq.r-1"
    assert rpatch["body"]["status"] == "replied"
    assert rpatch["body"]["aggregated_reply"] == "here is the board view"
    tpatch = sb.of("PATCH", "/intake_threads")[0]
    assert tpatch["params"]["id"] == "eq.th-1"
    assert tpatch["body"]["status"] == "awaiting_client"   # mapped from awaiting_partner


def test_mark_replied_ready_for_production_maps_thread_status():
    sb = FakeSb(rounds=[{"thread_id": "th-1"}])
    SupabaseRoundUpdater(sb_request=sb).mark_replied(
        round_id="r-1", aggregated_reply="ship it", next_action="ready_for_production")
    assert sb.of("PATCH", "/intake_threads")[0]["body"]["status"] == "ready_for_production"


def test_mark_failed_sets_failed_status():
    sb = FakeSb()
    SupabaseRoundUpdater(sb_request=sb).mark_failed(round_id="r-1", error="board down")
    patch = sb.of("PATCH", "/intake_board_rounds")[0]
    assert patch["params"]["id"] == "eq.r-1"
    assert patch["body"]["status"] == "failed"
    assert sb.of("PATCH", "/intake_threads") == []   # no thread advance on failure
