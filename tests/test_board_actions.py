"""Tests for app/server/agents/board_actions.py.

The Linear layer is mocked everywhere: no test in this file may reach the real
Linear API. `_no_linear` asserts that by making the real creator explode if any
path forgets to stub it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.server.agents import board_actions, board_meeting
from app.server.board_decision_index import BoardDecision, build_decision_index

SAMPLE_SWOT = """\
Phase 3 — SWOT ANALYSIS

**STRENGTHS**
- SDK-only path is enforced at startup
- Kill switches cover iterations, cost and a hard stop

WEAKNESSES:
- Phase 4 output dies in markdown
1. Route modules breach the 300-line convention

## OPPORTUNITIES
* Close the board -> Linear join

THREATS
- Ticket spam if the cap is removed
"""


def _recs(*rows: dict[str, str]) -> dict[str, str]:
    """A Phase-4 payload in the shape run_sprint_recommendations_phase returns."""
    return {
        "phase": "sprint_recommendations",
        "content": (
            "PRIORITY 1: RA-1 — do the thing — Estimate: S — Impact: high\n\n"
            "```json\n" + json.dumps(list(rows)) + "\n```\n"
        ),
    }


ROW_A = {"ticket": "RA-11", "title": "Close the board to Linear join",
         "rationale": "Phase 4 never files", "estimate": "M", "impact": "ZTE +3"}
ROW_B = {"ticket": "", "title": "Type the SWOT", "rationale": "Specs need structure",
         "estimate": "S", "impact": "spec quality"}
ROW_C = {"ticket": "", "title": "Seed skill proposals", "rationale": "Reuse meta_curator",
         "estimate": "S", "impact": "skill coverage"}
ROW_D = {"ticket": "", "title": "Fourth item", "rationale": "over the cap",
         "estimate": "XS", "impact": "none"}


@pytest.fixture(autouse=True)
def _no_linear(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test reaches the real Linear transport."""
    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("test reached the real Linear API")

    monkeypatch.setattr(board_meeting, "_linear_gql", _boom)
    monkeypatch.delenv("BOARD_FILE_SPRINT_RECS", raising=False)
    monkeypatch.delenv("BOARD_FILE_MACHINE_SHIP", raising=False)
    monkeypatch.delenv("BOARD_TICKET_CAP", raising=False)


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    """Capture every _linear_create_issue call instead of performing it."""
    calls: list[tuple[str, str, int]] = []

    def _create(title: str, description: str, priority: int) -> str:
        calls.append((title, description, priority))
        # The routing context manager must be active while this runs.
        assert board_meeting._LINEAR_PROJECT_ID == "f45212be-3259-4bfb-89b1-54c122c939a7"
        return f"RA-{900 + len(calls)}"

    monkeypatch.setattr(board_meeting, "_linear_create_issue", _create)
    monkeypatch.setattr(board_meeting, "_get_or_create_label", lambda _n: "label-uuid")
    monkeypatch.setattr(board_meeting, "_linear_apply_label", lambda _i, _l: True)
    return calls


@pytest.fixture
def clean_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decision index that nothing in these fixtures contradicts."""
    monkeypatch.setattr(
        board_actions, "build_decision_index",
        lambda: [BoardDecision("D1", "Unrelated locked thing", "body", "f.md", ["kangaroo"])],
    )


def test_emit_typed_swot_parses_all_four_quadrants() -> None:
    from swarm.intake.spm import SWOT

    swot = board_actions.emit_typed_swot(SAMPLE_SWOT)
    assert isinstance(swot, SWOT), "must reuse the existing typed dataclass"
    assert len(swot.strengths) == 2
    assert "Phase 4 output dies in markdown" in swot.weaknesses
    assert "Route modules breach the 300-line convention" in swot.weaknesses
    assert swot.opportunities == ["Close the board -> Linear join"]
    assert swot.threats == ["Ticket spam if the cap is removed"]
    assert board_actions.emit_typed_swot({"content": SAMPLE_SWOT}) == swot


@pytest.mark.parametrize("bad", ["", None, "no headings at all, just prose", {}, 17])
def test_emit_typed_swot_never_raises_on_junk(bad: Any) -> None:
    swot = board_actions.emit_typed_swot(bad)
    assert swot.strengths == [] and swot.threats == []


@pytest.mark.parametrize("dry_run,flag", [(True, None), (True, "1"), (False, None)])
def test_nothing_is_filed_without_both_dry_run_off_and_the_env_flag(
    created: list, clean_index: None, monkeypatch: pytest.MonkeyPatch,
    dry_run: bool, flag: str | None,
) -> None:
    if flag:
        monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", flag)
    out = board_actions.file_sprint_recommendations(_recs(ROW_A, ROW_B), dry_run=dry_run)
    assert created == []
    assert [r["action"] for r in out] == ["would_file", "would_file"]


def test_enabled_and_ready_files_up_to_the_cap(created, clean_index, monkeypatch) -> None:
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    out = board_actions.file_sprint_recommendations(
        _recs(ROW_A, ROW_B, ROW_C, ROW_D), dry_run=False,
    )
    filed = [r for r in out if r["action"] == "filed"]
    capped = [r for r in out if r["action"] == "capped"]
    assert len(created) == 3, f"cap breached: {created}"
    assert len(filed) == 3 and len(capped) == 1
    assert filed[0]["identifier"] == "RA-901"
    assert created[0][0].startswith("[SPRINT] ")


def test_cap_is_configurable_and_zero_files_nothing(created, clean_index, monkeypatch) -> None:
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    monkeypatch.setenv("BOARD_TICKET_CAP", "1")
    out = board_actions.file_sprint_recommendations(_recs(ROW_A, ROW_B), dry_run=False)
    assert len(created) == 1
    assert [r["action"] for r in out] == ["filed", "capped"]

    created.clear()
    monkeypatch.setenv("BOARD_TICKET_CAP", "0")
    out = board_actions.file_sprint_recommendations(_recs(ROW_A, ROW_B), dry_run=False)
    assert created == []
    assert {r["action"] for r in out} == {"capped"}


def test_recommendation_contradicting_a_mandate_is_blocked(created: list, monkeypatch) -> None:
    locked = BoardDecision(
        decision_id="OB-2", title="Rate limit — 3 autonomous PRs/day",
        body="MAX_AUTONOMOUS_PRS_PER_DAY=3 is locked until 20 green merges.",
        source_file="2026-04-15-activation-vote.md",
        keywords=["rate", "limit", "autonomous", "prs", "day", "merges", "locked"],
    )
    monkeypatch.setattr(board_actions, "build_decision_index", lambda: [locked])
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    offender = {
        "ticket": "", "title": "Remove the autonomous PRs per day rate limit",
        "rationale": "Lift the locked limit of 3 autonomous PRs per day for unlimited merges",
        "estimate": "S", "impact": "faster",
    }
    out = board_actions.file_sprint_recommendations(_recs(offender, ROW_B), dry_run=False)
    assert all("Remove" not in c[0] for c in created)
    assert out[0]["action"] == "blocked", out
    assert "OB-2" in out[0]["reason"]
    assert out[1]["action"] == "filed"


def test_unreadable_decision_corpus_blocks_everything(created: list, monkeypatch) -> None:
    def _raise() -> Any:
        raise RuntimeError("corpus missing")

    monkeypatch.setattr(board_actions, "build_decision_index", _raise)
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    out = board_actions.file_sprint_recommendations(_recs(ROW_A, ROW_B), dry_run=False)
    assert created == []
    assert {r["action"] for r in out} == {"blocked"}


@pytest.mark.parametrize("payload", [
    {"content": "PRIORITY 1: RA-1 — do it — Estimate: S — Impact: high"},   # prose only
    {"content": "```json\n[{'ticket': 'RA-1'},\n```"},                       # malformed JSON
    {"content": "```json\n{\"ticket\": \"RA-1\"}\n```"},                     # object, not array
    {"content": "```json\n[{\"title\": \"no rationale\"}]\n```"},            # missing field
    {"content": "```json\n[\"a string\", 42]\n```"},                         # not objects
    {"content": ""},
    None,
])
def test_malformed_phase4_payload_files_nothing(created, clean_index, monkeypatch, payload) -> None:
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    assert board_actions.file_sprint_recommendations(payload, dry_run=False) == []
    assert created == []


def test_machine_ship_label_needs_the_env_flag_and_readiness(created, clean_index, monkeypatch) -> None:
    import app.server.machine_ship_readiness as msr

    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    monkeypatch.setattr(msr, "machine_ship_readiness", lambda: {"ready": True, "blockers": []})
    label = lambda: board_actions.file_sprint_recommendations(  # noqa: E731
        _recs(ROW_A), dry_run=False)[0]["machine_ship"]
    assert label() is False, "label must stay off without BOARD_FILE_MACHINE_SHIP"

    monkeypatch.setenv("BOARD_FILE_MACHINE_SHIP", "1")
    monkeypatch.setattr(msr, "machine_ship_readiness", lambda: {"ready": False, "blockers": ["x"]})
    assert label() is False, "label must stay off when readiness fails"

    monkeypatch.setattr(msr, "machine_ship_readiness", lambda: {"ready": True, "blockers": []})
    assert label() is True


def test_ticket_body_carries_the_typed_swot(created, clean_index, monkeypatch) -> None:
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    swot = board_actions.emit_typed_swot(SAMPLE_SWOT)
    board_actions.file_sprint_recommendations(_recs(ROW_A), dry_run=False, swot=swot)
    body = created[0][1]
    assert "## SWOT (typed, Phase 3)" in body
    assert "Ticket spam if the cap is removed" in body


def test_create_failure_is_reported_not_raised(clean_index, monkeypatch) -> None:
    def _fail(*_a: Any, **_kw: Any) -> str:
        raise RuntimeError("Linear 500")

    monkeypatch.setattr(board_meeting, "_linear_create_issue", _fail)
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    out = board_actions.file_sprint_recommendations(_recs(ROW_A), dry_run=False)
    assert out[0]["action"] == "error"


def test_routing_resolves_by_project_id_not_repo() -> None:
    pi = board_actions._resolve_routing("pi-dev-ops")
    margot = board_actions._resolve_routing("margot")
    assert pi["project_id"] == "f45212be-3259-4bfb-89b1-54c122c939a7"
    assert margot["project_id"] == "94da87f8-a2a5-4fbb-9903-0047ff84d92c"
    assert pi["project_id"] != margot["project_id"], "same repo must not collapse to one project"
    assert board_actions._resolve_routing("CleanExpo/Pi-Dev-Ops") == {}
    assert board_actions._resolve_routing("no-such-id") == {}


def test_routing_is_scoped_and_a_missing_route_files_nothing(created, clean_index, monkeypatch) -> None:
    monkeypatch.setenv("BOARD_FILE_SPRINT_RECS", "1")
    before = (board_meeting._LINEAR_TEAM_ID, board_meeting._LINEAR_PROJECT_ID)
    board_actions.file_sprint_recommendations(_recs(ROW_A), dry_run=False, project_key="margot")
    assert (board_meeting._LINEAR_TEAM_ID, board_meeting._LINEAR_PROJECT_ID) == before

    created.clear()
    out = board_actions.file_sprint_recommendations(
        _recs(ROW_A), dry_run=False, project_key="oh-my-codex")
    assert created == []
    assert out[0]["action"] == "would_file"


def test_seed_skill_proposals_appends_board_tagged_lessons(tmp_path: Path, monkeypatch) -> None:
    from swarm import meta_curator

    target = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(meta_curator, "LESSONS_FILE", target)
    gaps = {
        "critical": [{"category": "observability", "recommendation": "Add the missing table"}],
        "high": [{"category": "routing", "reality": "no writeback", "recommendation": ""}],
        "low": [{"category": "docs", "recommendation": "Fix the stale row"}],
    }
    assert board_actions.seed_skill_proposals(gaps) == 3
    rows = [json.loads(ln) for ln in target.read_text().splitlines() if ln.strip()]
    assert {r["source"] for r in rows} == {"board"}
    assert {r["category"] for r in rows} == {"observability", "routing", "docs"}
    assert [r["severity"] for r in rows] == ["warn", "warn", "info"]
    assert all(r["ts"] and r["repo"] for r in rows)


def test_seed_skill_proposals_rows_survive_meta_curator_clustering(tmp_path, monkeypatch) -> None:
    """The rows must be shaped so the EXISTING weekly cron picks them up."""
    from swarm import meta_curator

    target = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(meta_curator, "LESSONS_FILE", target)
    gaps = [{"category": "routing", "recommendation": f"fix {n}"} for n in range(5)]
    assert board_actions.seed_skill_proposals(gaps) == 5
    clusters = meta_curator.scan_lessons()
    assert any(c.key.startswith("routing:") for c in clusters), clusters


@pytest.mark.parametrize("gaps", [None, {}, [], {"critical": []}, [{"category": "x"}], "junk"])
def test_seed_skill_proposals_ignores_empty_input(gaps: Any) -> None:
    assert board_actions.seed_skill_proposals(gaps) == 0


def test_real_governance_corpus_is_readable() -> None:
    """A null "nothing blocked" result is only evidence if the gate can load."""
    assert build_decision_index(), "decision corpus empty — the mandate gate is blind"
