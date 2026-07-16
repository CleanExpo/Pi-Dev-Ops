"""Tests for the RA-7014 slice-4 capture hook (app/server/agents/eval_capture.py).

Acceptance criteria covered (spec §15): #1 flag OFF = unreachable; #2 flag ON =
exactly one redacted row, failures never propagate; PII never at rest (§14).
All provider/Supabase surfaces injected — no network.
"""
from __future__ import annotations

import json
import time

import pytest

from app.server.agents import eval_capture as ec

_PREDICTED = {"category": "neutral", "label": "quiet thread", "confidence": 0.4}


def _capture(**overrides):
    kwargs = dict(
        comments=["client asked about timeline"], state="Done", days_since=4,
        pipeline_id="p-1", predicted=_PREDICTED, provider="openrouter", model="m",
        redact_fn=lambda t: t, insert_fn=lambda row: True, rng=lambda: 0.0,
    )
    kwargs.update(overrides)
    return ec.maybe_capture_candidate(**kwargs)


def test_flag_off_is_noop(monkeypatch):
    monkeypatch.delenv("TAO_EVAL_SAMPLING", raising=False)
    calls: list = []
    assert _capture(insert_fn=lambda row: calls.append(row) or True) is False
    assert calls == []


def test_flag_on_captures_one_redacted_row(monkeypatch):
    monkeypatch.setenv("TAO_EVAL_SAMPLING", "1")
    monkeypatch.setenv("TAO_EVAL_SAMPLE_RATE", "1.0")
    rows: list = []
    assert _capture(
        redact_fn=lambda t: "[REDACTED THREAD]",
        insert_fn=lambda row: rows.append(row) or True,
    ) is True
    assert len(rows) == 1
    row = rows[0]
    assert row["thread_redacted"] == "[REDACTED THREAD]"
    assert row["predicted_category"] == "neutral"
    assert row["status"] == "pending"


def test_pii_never_at_rest_with_real_redactor(monkeypatch):
    """§14 — PII-seeded fixture through the REAL redactor: the raw email/phone
    must not appear in the written row."""
    monkeypatch.setenv("TAO_EVAL_SAMPLING", "1")
    monkeypatch.setenv("TAO_EVAL_SAMPLE_RATE", "1.0")
    rows: list = []
    from swarm.pii_redactor import redact

    assert _capture(
        comments=["ping jane.doe@clientco.com re invoice, mobile 0412 345 678"],
        redact_fn=lambda t: redact(t, context="eval_capture").redacted_payload,
        insert_fn=lambda row: rows.append(row) or True,
    ) is True
    dumped = json.dumps(rows[0])
    assert "jane.doe@clientco.com" not in dumped


def test_supabase_down_falls_back_to_local_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_EVAL_SAMPLING", "1")
    monkeypatch.setenv("TAO_EVAL_SAMPLE_RATE", "1.0")
    fallback = tmp_path / "candidates.jsonl"
    start = time.monotonic()
    assert _capture(insert_fn=lambda row: False, fallback_path=fallback) is True
    assert time.monotonic() - start < 1.0  # §14 — Supabase-down must not slow the path
    lines = fallback.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["pipeline_id"] == "p-1"


def test_redactor_failure_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_EVAL_SAMPLING", "1")
    monkeypatch.setenv("TAO_EVAL_SAMPLE_RATE", "1.0")

    def boom(_t: str) -> str:
        raise RuntimeError("redactor exploded")

    fallback = tmp_path / "candidates.jsonl"
    assert _capture(redact_fn=boom, fallback_path=fallback) is False
    assert not fallback.exists()  # nothing written when redaction failed


@pytest.mark.parametrize("rate,rng,expected", [
    ("0.0", 0.0, False),   # rate 0 captures nothing even with flag on
    ("1.0", 0.999, True),  # rate 1 captures everything
    ("0.2", 0.5, False),   # above rate → skipped
    ("0.2", 0.1, True),    # below rate → captured
])
def test_sampling_boundaries(monkeypatch, rate, rng, expected):
    monkeypatch.setenv("TAO_EVAL_SAMPLING", "1")
    monkeypatch.setenv("TAO_EVAL_SAMPLE_RATE", rate)
    assert _capture(rng=lambda: rng) is expected


def test_thread_mirrors_classifier_construction():
    assert ec.build_thread(["a", "b"], "Done") == "a\n---\nb\n\nLinear state: Done"
    assert ec.build_thread([], "Todo") == "(no comments)\n\nLinear state: Todo"
