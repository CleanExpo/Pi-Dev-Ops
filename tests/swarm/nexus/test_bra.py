"""Focused tests for swarm.nexus.bra — BRA generator with evidence anchoring."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from swarm.nexus.bra import BRAReport, generate_bra
from swarm.nexus.outcomes import InMemoryOutcomesStore
from swarm.nexus.types import Outcome


NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc).isoformat()


# ============================================================
# Stub LLM
# ============================================================


class StubLLM:
    def __init__(self, response: object):
        self._resp = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
        self.calls.append((system, user))
        if isinstance(self._resp, Exception):
            raise self._resp
        if isinstance(self._resp, str):
            return self._resp
        return json.dumps(self._resp)


# ============================================================
# Helpers
# ============================================================


def _outcome(id_: str, **kw) -> Outcome:
    base = dict(
        id=id_,
        workspace_id="ws-1",
        workspace_slug="acme",
        source="stripe",
        metric="mrr",
        captured_at=NOW,
        value_numeric=199.0,
    )
    base.update(kw)
    return Outcome(**base)


def _card(brief="b", rec="r", act="a", sev="medium", evidence=("out-1",)):
    return {
        "brief": brief, "recommendation": rec, "action": act,
        "severity": sev, "evidence_ids": list(evidence),
    }


# ============================================================
# Tests
# ============================================================


class TestGenerateBRA:
    def test_no_outcomes_returns_empty_report(self):
        store = InMemoryOutcomesStore()
        llm = StubLLM({"cards": []})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert isinstance(report, BRAReport)
        assert report.cards == ()
        assert llm.calls == [], "LLM should not be called when no outcomes"

    def test_happy_path_returns_anchored_card(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM({"cards": [_card(evidence=("out-1",))]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert len(report.cards) == 1
        assert report.cards[0].evidence_ids == ("out-1",)

    def test_unanchored_evidence_card_dropped(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        # LLM cites a fabricated id
        llm = StubLLM({"cards": [_card(evidence=("hallucinated-id",))]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert report.cards == ()
        assert report.dropped_unanchored == 1

    def test_mixed_evidence_keeps_card_with_valid_ids_only(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        store.write(_outcome("out-2"))
        llm = StubLLM({"cards": [
            _card(evidence=("out-1", "ghost", "out-2")),
        ]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert len(report.cards) == 1
        assert report.cards[0].evidence_ids == ("out-1", "out-2")

    def test_severity_ranking_most_severe_first(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM({"cards": [
            _card(sev="low",      evidence=("out-1",), brief="a"),
            _card(sev="critical", evidence=("out-1",), brief="b"),
            _card(sev="medium",   evidence=("out-1",), brief="c"),
            _card(sev="high",     evidence=("out-1",), brief="d"),
        ]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        severities = [c.severity for c in report.cards]
        assert severities == ["critical", "high", "medium", "low"]

    def test_malformed_card_dropped(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        # missing required keys
        llm = StubLLM({"cards": [{"brief": "x"}, _card(evidence=("out-1",))]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert len(report.cards) == 1
        assert report.dropped_malformed == 1

    def test_invalid_severity_dropped(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM({"cards": [_card(sev="apocalyptic", evidence=("out-1",))]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert report.cards == ()
        assert report.dropped_malformed == 1

    def test_llm_exception_returns_empty_report(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM(ConnectionError("anthropic 503"))
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert report.cards == ()
        assert report.dropped_malformed == 1

    def test_llm_malformed_json_returns_empty_report(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM("not json at all")
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert report.cards == ()
        assert report.dropped_malformed == 1

    def test_llm_missing_cards_key_returns_empty_report(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM({"oops": "no cards field"})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert report.cards == ()
        assert report.dropped_malformed == 1

    def test_workspace_filter_respected(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1", workspace_slug="acme"))
        store.write(_outcome("out-2", workspace_slug="other"))
        llm = StubLLM({"cards": [_card(evidence=("out-1",))]})
        report = generate_bra(
            workspace_slug="acme", window="7d",
            outcomes_store=store, llm=llm,
        )
        assert len(report.cards) == 1
        # Confirm the user prompt only includes 'acme' outcomes:
        _system, user_msg = llm.calls[0]
        assert "out-1" in user_msg
        assert "out-2" not in user_msg

    def test_window_passed_through_to_report(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome("out-1"))
        llm = StubLLM({"cards": []})
        for window in ("24h", "7d", "30d"):
            report = generate_bra(
                workspace_slug="acme", window=window,
                outcomes_store=store, llm=llm,
            )
            assert report.window == window
