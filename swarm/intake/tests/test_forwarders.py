"""Contract tests for BoardSpmForwarder — the concrete SpmForwarder that
turns a `forward_to_spm` hand-off into an SPM brief + an enqueued Board
deliberation, persisting the round.

Async board model: the forwarder enqueues a board round and records it;
it does NOT wait for minutes or send the partner reply (that happens on a
later advance-waiting-threads tick). Forward is fire-and-forget.
"""
import json

from swarm.intake.forwarders import BoardSpmForwarder
from swarm.intake.spm import ProjectContext, ThreadMessage


# ── Fakes ────────────────────────────────────────────────────────────────────
_SPM_JSON = json.dumps({
    "layout": "single-page",
    "framework": "next",
    "suitability": "good fit",
    "swot": {"strengths": ["s1"], "weaknesses": [], "opportunities": [], "threats": []},
    "open_questions": ["What is the budget?", "Launch date?"],
    "ready_for_production": False,
    "rationale": "Solid early signal.",
})


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, *, system, user, max_tokens=1500, temperature=0.3):
        self.calls += 1
        return _SPM_JSON


class FakeProjectLoader:
    def __init__(self, project):
        self._project = project
        self.calls = []

    def load_project(self, *, project_id):
        self.calls.append(project_id)
        return self._project


class FakeMessageLoader:
    def __init__(self, messages):
        self._messages = messages
        self.calls = []

    def recent_messages(self, *, thread_id, limit=30):
        self.calls.append(thread_id)
        return self._messages


class FakeRoundStore:
    def __init__(self):
        self.rounds = []

    def record_round(self, *, thread_id, project_id, bot_id, board_id, brief):
        self.rounds.append({
            "thread_id": thread_id, "project_id": project_id,
            "bot_id": bot_id, "board_id": board_id, "brief": brief,
        })


def _project():
    return ProjectContext(
        project_id="proj-1",
        workspace_slug="duncan-acme",
        name="Acme Portal",
        slug="acme-portal",
        owner_partner_id="partner_duncan",
        description="A client portal",
        status="discovery",
    )


def _messages():
    return [ThreadMessage(
        direction="inbound", author="client", body="We need a portal",
        submitted_by_partner_id="partner_duncan", created_at="2026-06-29T00:00:00Z",
    )]


def _forwarder(*, board_submit, round_store, llm=None, enabled=lambda: True,
               kill_switch=lambda: False, should_skip=lambda tid: False,
               project_loader=None, message_loader=None):
    return BoardSpmForwarder(
        project_loader=project_loader or FakeProjectLoader(_project()),
        message_loader=message_loader or FakeMessageLoader(_messages()),
        round_store=round_store,
        llm=llm or FakeLLM(),
        board_submit=board_submit,
        kill_switch=kill_switch,
        enabled=enabled,
        should_skip_debounce=should_skip,
    )


# ── Happy path ───────────────────────────────────────────────────────────────
def test_forward_builds_brief_enqueues_board_and_records_round():
    submitted = []

    def board_submit(*, topic, insight, requested_decisions):
        submitted.append({"topic": topic, "insight": insight,
                          "requested_decisions": requested_decisions})
        return "board-123"

    store = FakeRoundStore()
    llm = FakeLLM()
    fwd = _forwarder(board_submit=board_submit, round_store=store, llm=llm)

    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hello")

    assert llm.calls == 1, "SPM brief must be built via the LLM"
    assert len(submitted) == 1, "board deliberation must be enqueued exactly once"
    assert submitted[0]["topic"] == "Acme Portal"
    # open_questions from the brief flow through as requested_decisions
    assert submitted[0]["requested_decisions"] == ["What is the budget?", "Launch date?"]
    assert len(store.rounds) == 1
    assert store.rounds[0]["board_id"] == "board-123"
    assert store.rounds[0]["thread_id"] == "th-1"
    assert store.rounds[0]["project_id"] == "proj-1"
    assert store.rounds[0]["bot_id"] == "bot-1"


def test_brief_content_is_in_the_board_insight():
    captured = {}

    def board_submit(*, topic, insight, requested_decisions):
        captured["insight"] = insight
        return "board-x"

    fwd = _forwarder(board_submit=board_submit, round_store=FakeRoundStore())
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    # The board must receive the SPM assessment, not the raw client message.
    assert "Solid early signal." in captured["insight"]  # rationale
    assert "single-page" in captured["insight"]           # layout


# ── Gating / safety ──────────────────────────────────────────────────────────
def test_disabled_flag_is_noop():
    submitted = []
    store = FakeRoundStore()
    fwd = _forwarder(
        board_submit=lambda **k: submitted.append(k) or "x",
        round_store=store, enabled=lambda: False,
    )
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    assert submitted == []
    assert store.rounds == []


def test_kill_switch_skips_fanout():
    submitted = []
    store = FakeRoundStore()
    fwd = _forwarder(
        board_submit=lambda **k: submitted.append(k) or "x",
        round_store=store, kill_switch=lambda: True,
    )
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    assert submitted == []
    assert store.rounds == []


def test_debounce_skips_fanout():
    submitted = []
    store = FakeRoundStore()
    fwd = _forwarder(
        board_submit=lambda **k: submitted.append(k) or "x",
        round_store=store, should_skip=lambda tid: True,
    )
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    assert submitted == []
    assert store.rounds == []


# ── Fire-and-forget ──────────────────────────────────────────────────────────
def test_board_failure_is_swallowed_and_no_round_recorded():
    def board_submit(*, topic, insight, requested_decisions):
        raise RuntimeError("board queue down")

    store = FakeRoundStore()
    fwd = _forwarder(board_submit=board_submit, round_store=store)
    # Must not raise — fire-and-forget per the SpmForwarder contract.
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    assert store.rounds == [], "no round persisted when the board enqueue fails"


def test_loader_failure_is_swallowed():
    class BoomLoader:
        def load_project(self, *, project_id):
            raise RuntimeError("db down")

    store = FakeRoundStore()
    fwd = _forwarder(
        board_submit=lambda **k: "x", round_store=store,
        project_loader=BoomLoader(),
    )
    fwd.forward(thread_id="th-1", project_id="proj-1", bot_id="bot-1", body="hi")
    assert store.rounds == []
