"""Contract tests for SupabaseBoardRoundStore — the BoardRoundStore adapter
that persists one `intake_board_rounds` row per enqueued board deliberation.

The adapter derives `client_slug` and the next `round_number` from the
`intake_threads` row (the SpmForwarder Protocol does not pass them), then
inserts the round and advances the thread's `board_rounds` counter. All
Supabase I/O is injected so these tests never touch a real DB.
"""
import json

import pytest

from swarm.intake.round_store import SupabaseBoardRoundStore
from swarm.intake.spm import SPMBrief, SWOT


# ── Fakes ────────────────────────────────────────────────────────────────────
class FakeSb:
    """Stand-in for intake_router._sb_request."""
    def __init__(self, thread_row=None):
        self.calls = []
        self._thread_row = thread_row

    def __call__(self, method, path, params=None, body=None, extra_headers=None):
        self.calls.append({
            "method": method, "path": path, "params": params,
            "body": body, "extra_headers": extra_headers,
        })
        if method == "GET" and path == "/intake_threads":
            return [self._thread_row] if self._thread_row is not None else []
        return None

    def posts_to(self, path):
        return [c for c in self.calls if c["method"] == "POST" and c["path"] == path]

    def patches_to(self, path):
        return [c for c in self.calls if c["method"] == "PATCH" and c["path"] == path]


def _brief():
    return SPMBrief(
        layout="single-page", framework="next", suitability="good fit",
        swot=SWOT(strengths=["s1"], weaknesses=["w1"], opportunities=[], threats=[]),
        open_questions=["budget?"], ready_for_production=False,
        rationale="solid",
    )


def _store(thread_row, *, id_factory=lambda: "icbr_fixed"):
    sb = FakeSb(thread_row=thread_row)
    return SupabaseBoardRoundStore(sb_request=sb, id_factory=id_factory), sb


def _record(store):
    store.record_round(
        thread_id="th-1", project_id="proj-1", bot_id="bot-1",
        board_id="board-9", brief=_brief(),
    )


# ── Happy path ───────────────────────────────────────────────────────────────
def test_inserts_round_with_derived_fields():
    store, sb = _store({"client_slug": "duncan-acme", "board_rounds": 0})
    _record(store)

    posts = sb.posts_to("/intake_board_rounds")
    assert len(posts) == 1
    row = posts[0]["body"]
    assert row["id"] == "icbr_fixed"
    assert row["thread_id"] == "th-1"
    assert row["client_slug"] == "duncan-acme"      # derived from the thread
    assert row["round_number"] == 1                  # board_rounds(0) + 1
    assert row["board_session_id"] == "board-9"
    assert row["status"] == "requested"


def test_spm_brief_serialized_as_json_object():
    store, sb = _store({"client_slug": "acme", "board_rounds": 0})
    _record(store)
    row = sb.posts_to("/intake_board_rounds")[0]["body"]
    brief = row["spm_brief"]
    # JSON-serializable nested dataclass (asdict), not a frozen SPMBrief.
    json.dumps(brief)
    assert brief["layout"] == "single-page"
    assert brief["swot"]["strengths"] == ["s1"]


def test_round_number_increments_from_thread_counter():
    store, sb = _store({"client_slug": "acme", "board_rounds": 2})
    _record(store)
    assert sb.posts_to("/intake_board_rounds")[0]["body"]["round_number"] == 3


def test_thread_board_rounds_counter_advanced():
    store, sb = _store({"client_slug": "acme", "board_rounds": 2})
    _record(store)
    patches = sb.patches_to("/intake_threads")
    assert len(patches) == 1
    assert patches[0]["params"] == {"id": "eq.th-1"}
    assert patches[0]["body"] == {"board_rounds": 3}


def test_unique_id_minted_per_round():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return f"icbr_{counter['n']}"

    store, sb = _store({"client_slug": "acme", "board_rounds": 0}, id_factory=factory)
    _record(store)
    store2_sb = FakeSb({"client_slug": "acme", "board_rounds": 1})
    store2 = SupabaseBoardRoundStore(sb_request=store2_sb, id_factory=factory)
    store2.record_round(thread_id="th-1", project_id="p", bot_id="b",
                        board_id="x", brief=_brief())
    ids = [sb.posts_to("/intake_board_rounds")[0]["body"]["id"],
           store2_sb.posts_to("/intake_board_rounds")[0]["body"]["id"]]
    assert ids == ["icbr_1", "icbr_2"]


# ── Failure handling ─────────────────────────────────────────────────────────
def test_missing_thread_raises_and_inserts_nothing():
    store, sb = _store(None)  # GET returns []
    with pytest.raises(ValueError):
        _record(store)
    assert sb.posts_to("/intake_board_rounds") == []
    assert sb.patches_to("/intake_threads") == []
