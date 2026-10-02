"""Round 27 P1-JEV-DUPLICATE-LABELLER-ANSWER-ACCEPTED: model-written JSON with a duplicate key is malformed.

{"labels":[false],"labels":[true]} read as true, so a contradictory blind label agreed with the writer and
became ground truth, and writer-control scored contradiction as agreement. Every JSON parse in Jev now
refuses duplicate keys. Offline: the Codex subprocess is faked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.jev_constitution import generate, writer_control
from jev_platform import client

Q = {"id": "t-01", "quote": "q", "question": "Does it comply?", "criteria_true": "y", "criteria_false": "n"}


def test_strict_json_raises_a_decode_error_on_any_duplicate():
    for raw in ['{"a":1,"a":2}', '[{"x":{"b":1,"b":1}}]']:
        with pytest.raises(json.JSONDecodeError):
            client.strict_json(raw)
    assert client.strict_json('{"a":1,"b":[{"a":2}]}') == {"a": 1, "b": [{"a": 2}]}


def test_codex_label_refuses_contradictory_duplicate_labels(monkeypatch):
    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_text('{"labels":[false],"labels":[true]}')
    monkeypatch.setattr(generate.subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        generate.codex_label(Q, ["one scenario"])


def test_codex_label_still_reads_a_clean_reply(monkeypatch):
    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_text('{"labels":[true]}')
    monkeypatch.setattr(generate.subprocess, "run", fake_run)
    assert generate.codex_label(Q, ["one scenario"]) == [True]


def test_writer_cases_with_a_duplicate_label_field_are_refused():
    with pytest.raises(ValueError):
        generate.parse_cases('[{"state":"s","label":false,"label":true}]')


def test_writer_control_counts_a_duplicate_reply_as_malformed():
    stats = {"requested": 0, "admitted_by_class": {}, "malformed": 0}
    entry = {"class": "normal", "violation": 1, "compliant": 1}
    writer_control._score_entry(stats, entry, '[{"state":"s","label":true,"label":false}]', lambda s: True)
    assert stats["malformed"] == 2
