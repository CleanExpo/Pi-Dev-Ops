"""Contract tests for BoardReplyTick — the advance-waiting-threads step.

When a board round (enqueued by BoardSpmForwarder) completes, this tick
distills the minutes via aggregate_board_response and delivers the
partner-facing reply, then marks the round replied. The board is async, so
the tick polls get_completed and skips rounds still deliberating.

All collaborators are injected; the real spm.aggregate_board_response runs
with a fake LLM (canned JSON), so these tests exercise the genuine
aggregation path without network or DB.
"""
import json
from types import SimpleNamespace

from swarm.intake.board_reply import BoardReplyTick, PendingRound
from swarm.intake.spm import ProjectContext, SPMBrief, SWOT


_AGG_JSON = json.dumps({
    "summary_for_partner": "The board recommends proceeding with a phased build.",
    "open_questions": ["Confirm the launch date?"],
    "next_action": "awaiting_partner",
    "metadata": {"board_personas_aligned": 7, "board_personas_dissenting": 2},
})


class FakeLLM:
    def __init__(self, payload=_AGG_JSON):
        self.calls = 0
        self._payload = payload

    def complete(self, *, system, user, max_tokens=1500, temperature=0.3):
        self.calls += 1
        return self._payload


class FakeReply:
    def __init__(self):
        self.sent = []

    def send(self, *, thread_id, text):
        self.sent.append({"thread_id": thread_id, "text": text})


class FakeUpdater:
    def __init__(self):
        self.replied = []
        self.failed = []

    def mark_replied(self, *, round_id, aggregated_reply, next_action):
        self.replied.append({"round_id": round_id, "aggregated_reply": aggregated_reply,
                             "next_action": next_action})

    def mark_failed(self, *, round_id, error):
        self.failed.append({"round_id": round_id, "error": error})


def _project():
    return ProjectContext(
        project_id="proj-1", workspace_slug="duncan-acme", name="Acme Portal",
        slug="acme-portal", owner_partner_id="partner_duncan",
        description="portal", status="in_board",
    )


def _brief():
    return SPMBrief(
        layout="single-page", framework="next", suitability="fit",
        swot=SWOT(strengths=["s"], weaknesses=[], opportunities=[], threats=[]),
        open_questions=["budget?"], ready_for_production=False, rationale="solid",
    )


def _round(round_id="r-1", session_id="board-1"):
    return PendingRound(
        round_id=round_id, thread_id="th-1", board_session_id=session_id,
        requesting_partner_id="partner_duncan", project=_project(), spm_brief=_brief(),
    )


def _session(*, succeeded=True, deliberation="full debate text", summary="summary"):
    return SimpleNamespace(
        deliberation_text=deliberation, minutes_summary=summary,
        succeeded=lambda: succeeded,
    )


def _tick(*, rounds, checker, llm=None, reply=None, updater=None):
    return BoardReplyTick(
        pending_rounds=lambda: rounds,
        completion_checker=checker,
        llm=llm or FakeLLM(),
        reply=reply or FakeReply(),
        round_updater=updater or FakeUpdater(),
    )


# ── Happy path ───────────────────────────────────────────────────────────────
def test_completed_round_aggregates_replies_and_marks_replied():
    reply, updater, llm = FakeReply(), FakeUpdater(), FakeLLM()
    checks = []
    def checker(sid):
        checks.append(sid)
        return _session()
    tick = _tick(rounds=[_round()], checker=checker, llm=llm, reply=reply, updater=updater)

    result = tick.run_once()

    assert checks == ["board-1"]
    assert llm.calls == 1                       # real aggregate_board_response ran
    assert len(reply.sent) == 1
    assert reply.sent[0]["thread_id"] == "th-1"
    assert "phased build" in reply.sent[0]["text"]
    assert len(updater.replied) == 1
    assert updater.replied[0]["round_id"] == "r-1"
    assert updater.replied[0]["next_action"] == "awaiting_partner"
    assert result.replied == 1 and result.pending == 0


# ── Still deliberating ───────────────────────────────────────────────────────
def test_incomplete_round_is_skipped():
    reply, updater = FakeReply(), FakeUpdater()
    tick = _tick(rounds=[_round()], checker=lambda sid: None, reply=reply, updater=updater)
    result = tick.run_once()
    assert reply.sent == []
    assert updater.replied == []
    assert result.pending == 1 and result.replied == 0


# ── Board errored ────────────────────────────────────────────────────────────
def test_failed_session_marks_failed_no_reply():
    reply, updater = FakeReply(), FakeUpdater()
    tick = _tick(rounds=[_round()], checker=lambda sid: _session(succeeded=False),
                 reply=reply, updater=updater)
    result = tick.run_once()
    assert reply.sent == []
    assert len(updater.failed) == 1
    assert updater.replied == []
    assert result.failed == 1


# ── Minutes fallback ─────────────────────────────────────────────────────────
def test_uses_minutes_summary_when_deliberation_text_empty():
    captured = {}

    class CapturingLLM(FakeLLM):
        def complete(self, *, system, user, max_tokens=1500, temperature=0.3):
            captured["user"] = user
            return _AGG_JSON

    tick = _tick(rounds=[_round()],
                 checker=lambda sid: _session(deliberation="", summary="the summary minutes"),
                 llm=CapturingLLM())
    tick.run_once()
    assert "the summary minutes" in captured["user"]


# ── Fire-and-forget per round ────────────────────────────────────────────────
def test_one_round_failure_does_not_block_others():
    reply, updater = FakeReply(), FakeUpdater()

    def checker(sid):
        if sid == "board-bad":
            raise RuntimeError("disk error")
        return _session()

    rounds = [_round(round_id="r-bad", session_id="board-bad"),
              _round(round_id="r-good", session_id="board-good")]
    tick = _tick(rounds=rounds, checker=checker, reply=reply, updater=updater)
    result = tick.run_once()

    assert [r["round_id"] for r in updater.replied] == ["r-good"]
    assert result.replied == 1
    assert result.errored == 1
