"""RA-8100 D56: the two contradictions the re-screen of 75360561 showed were still accepted, as tests.

1. A swept open pull whose author's type says Bot while the login is a person's was counted away as a bot
   pull: no record, no alert, and the tick still read complete.
2. A stored commit ID, time, age source or link could be any text: a merged record whose SHAs were the text
   ``verified-ok`` loaded and showed on the tile.
Both fail on 75360561 (evidence/build/red-first-rescreen-75360561.log).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import test_delivery_invariant_scenes as scenes
from _delivery_reconcile_support import NOW, PIDEV, open_pull, orphan_item, run, sweep_path
from _delivery_stored_support import planted, stored

from app.server import delivery_invariants as inv
from app.server import delivery_reconcile_schema as schema
from app.server import delivery_stage as ds

BOT, PERSON = "dependabot[bot]", "someone"


def _orphan(login: str, kind: str) -> dict:
    item = {**orphan_item(9, author_type=kind), "author_login": login}
    record, _found = ds.classify(None, [item], {"revision": None, "compare": {}}, NOW, repo=PIDEV,
                                 project_id="proj", first_seen=None)
    return record


def test_only_a_bot_by_login_and_by_type_is_counted_away() -> None:
    record = _orphan(BOT, "Bot")
    assert (record["stage"], record["counted"]) == ("counted", "bot_prs")


@pytest.mark.parametrize(("login", "kind"), [(PERSON, "Bot"), (BOT, "User"), (PERSON, "User"), (BOT, "Mannequin")])
def test_an_author_whose_login_and_type_disagree_is_placed_never_counted_away(login: str, kind: str) -> None:
    record = _orphan(login, kind)
    assert (record["stage"], record["counted"]) == ("building", None)  # a record on the tile, not a tally


@pytest.mark.parametrize(("user", "bot"), [
    ({"login": BOT, "type": "Bot"}, True), ({"login": PERSON, "type": "Bot"}, False),
    ({"login": BOT, "type": "User"}, False), ({"login": None, "type": None}, False), ({}, False), (None, False),
    ({"login": 5, "type": "Bot"}, False),
])
def test_the_reading_is_one_row_of_the_list(user: object, bot: bool) -> None:
    assert inv.reading("author_is_bot", user) is bot


def _state(**fields: object) -> dict:
    return planted({"RA-1": stored({"id": "RA-1", **fields})})


def _alerted(**fields: object) -> dict:
    alert = stored({"key": "K", "mission_id": "RA-1", "code": "UNOWNED", "ref": "RA-1", **fields}, alert=True)
    return planted({"RA-1": stored({"id": "RA-1"})}, {"K": alert})


def test_the_planted_states_are_sound_before_a_field_is_spoiled() -> None:
    assert schema.problems(_state()) == [] and schema.problems(_alerted()) == []
    assert schema.problems(_state(stage="merged")) == []
    assert schema.problems(_alerted(since="2026-11-14T00:00:00Z", age_source="startedAt",
                                    url=f"https://github.com/{PIDEV}/pull/7")) == []


@pytest.mark.parametrize("fields", [
    {"pr_head_sha": "verified-ok"}, {"pr_head_sha": "A" * 40}, {"pr_head_sha": "a" * 39}, {"pr_head_sha": ""},
    {"stage": "merged", "merge_sha": "verified-ok"},
    {"stage": "merged", "merge_sha": "verified-ok", "deployed_sha": "verified-ok", "verified_sha": "verified-ok"},
    {"stage": "approval_wait", "reviewed_head_sha": "approved", "pr_head_sha": "approved"},
    {"since": "yesterday"}, {"since": ""}, {"since": "2026-11-14T00:00:00"}, {"since": "2026-11-14T10:00:00+10:00"},
    {"since": "2026-11-14"}, {"age_source": "trust me"},
])
def test_a_stored_record_field_outside_its_domain_is_not_a_state(fields: dict) -> None:
    assert schema.problems(_state(**fields)) != []


@pytest.mark.parametrize("fields", [
    {"since": "yesterday", "age_source": "startedAt"}, {"since": "2026-11-14T00:00:00Z", "age_source": "trust me"},
    {"url": "verified-ok"}, {"url": "http://github.com/a/b/pull/1"}, {"url": "https://example.com/a/b/pull/1"},
    {"url": f"https://github.com/{PIDEV}/pull/0"}, {"url": f"https://github.com/{PIDEV}/pull/7/files"},
    {"url": ""},
])
def test_a_stored_alert_field_outside_its_domain_is_not_a_state(fields: dict) -> None:
    assert schema.problems(_alerted(**fields)) != []


@pytest.mark.parametrize(("login", "kind", "placed"), [(PERSON, "Bot", True), (BOT, "User", True), (BOT, "Bot", False)])
def test_on_a_whole_tick_only_a_bot_by_both_is_counted_away(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                            login: str, kind: str, placed: bool) -> None:
    """The re-screen's own case, through the real readers: the sweep answers one open pull no mission links."""
    st = scenes._world(monkeypatch, tmp_path)
    scenes._scene(st, sorted(scenes.SCENES)[0])
    st.gh[sweep_path(PIDEV)] = [{**open_pull(9), "user": {"login": login, "type": kind}}]
    state = scenes._saved_and_whole(st, run(st))
    assert (f"pr:{PIDEV}#9" in state["missions"], state["summary"]["bot_prs"]) == (placed, 0 if placed else 1)
