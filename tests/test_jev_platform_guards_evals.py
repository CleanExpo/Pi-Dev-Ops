"""Guard sweep 29/09: every eval-pipeline guard in evals/jev_constitution has a test that fails without it.

Offline: a fake codex subprocess, a fake Gemini transport, tmp git repos. No key, no CLI, no network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess

import pytest
from jev_scale_support import FakeGemini, ftext

from evals.jev_constitution import generate, harness, quotes
from evals.jev_constitution import writer_control as wc
from jev_platform import gemini

QUESTION = {"id": "core-44", "quote": "A narrow, named delegation.", "question": "Does it comply?",
            "criteria_true": "Used only to mark a verified PR ready", "criteria_false": "Used for spend or merge"}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


# ---- quotes.py

def test_a_symlinked_constitution_is_read_through_to_its_target(tmp_path):
    """The symlink's own blob is a path, never the rule text a quote is checked against."""
    (tmp_path / "docs" / "constitution").mkdir(parents=True)
    (tmp_path / "docs" / "constitution" / "EPIC-000.md").write_text("The real rule body.\n")
    os.symlink("docs/constitution/EPIC-000.md", tmp_path / "CONSTITUTION.md")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "c")
    assert quotes.read_source(str(tmp_path), "HEAD", "CONSTITUTION.md") == "The real rule body.\n"


def _quotes_main(monkeypatch, tmp_path, stored: bool) -> int:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"constitution": "rev abcdef123",
                                "questions": [{"id": "q1", "quote_verbatim": stored}]}))
    monkeypatch.setattr(harness, "QUESTIONS", path)
    monkeypatch.setattr(quotes, "check", lambda data, repo: {"q1": None})  # the source says verbatim
    return quotes.main(["--repo", str(tmp_path)])


def test_quote_check_exits_1_when_a_stored_flag_drifts(monkeypatch, tmp_path):
    assert _quotes_main(monkeypatch, tmp_path, stored=False) == 1
    assert _quotes_main(monkeypatch, tmp_path, stored=True) == 0


# ---- harness.py

def test_a_non_200_reply_is_never_a_judgment_even_with_a_valid_answer():
    valid = {"answers": {"q": {"type": "noul", "noul": 0.9}}}
    status, noul, _ = harness.ask_jev(QUESTION, "s", "k", post=lambda body, key: (500, valid))
    assert (status, noul) == (500, None)
    assert harness.ask_jev(QUESTION, "s", "k", post=lambda body, key: (200, valid))[1] == 0.9


def test_validate_exits_invalid_on_an_unscoreable_case_set(monkeypatch, tmp_path, capsys):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": [{"id": "q1", "quote_verbatim": True}]}))
    monkeypatch.setattr(harness, "QUESTIONS", path)
    monkeypatch.setattr(harness, "CASES", tmp_path / "cases")  # no cases at all
    assert harness.main(["validate"]) == harness.EXIT_INVALID
    assert "INVALID q1" in capsys.readouterr().out


# ---- generate.py: env, parsing, Gemini reply

def test_the_cli_env_never_carries_an_api_key(monkeypatch):
    for k in generate._SCRUB:
        monkeypatch.setenv(k, "sk-test-not-a-real-key")
    monkeypatch.setenv("JEV_GUARD_SWEEP_KEEP", "1")
    env = generate._env()
    assert not set(generate._SCRUB) & set(env) and env["JEV_GUARD_SWEEP_KEEP"] == "1"


def test_a_json_object_reply_is_refused_not_counted_as_malformed():
    with pytest.raises(ValueError, match="not a JSON array"):
        generate.parse_cases('{"a": 1}')


def _reply(parts, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": ftext("x")["usageMetadata"]}


def _gem_budget():
    return gemini.GeminiBudget(gemini.WRITER_CAP_USD, gemini.price_table(dt.date(2026, 10, 1)))


def test_a_truncated_gemini_reply_is_refused():
    fake = FakeGemini([_reply([{"text": '[{"state": "a", "label": true}]'}], finish="MAX_TOKENS")])
    with pytest.raises(ValueError, match="truncated"):
        generate.gemini_text("write cases", _gem_budget(), fake, "gk-test-not-a-real-key")


def test_gemini_thought_text_is_never_part_of_the_reply():
    fake = FakeGemini([_reply([{"text": "SECRET REASONING", "thought": True}, {"text": "[]"}])])
    assert generate.gemini_text("write cases", _gem_budget(), fake, "gk-test-not-a-real-key") == "[]"


# ---- generate.py: codex labels

def _fake_codex(monkeypatch, labels):
    def run(args, **kw):
        with open(args[args.index("-o") + 1], "w") as f:
            f.write(json.dumps({"labels": labels}))
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(generate.subprocess, "run", run)


def test_codex_returning_the_wrong_count_labels_nothing(monkeypatch):
    _fake_codex(monkeypatch, [True])
    assert generate.codex_label(QUESTION, ["a", "b"]) == [None, None]


def test_a_non_bool_codex_label_is_no_label(monkeypatch):
    _fake_codex(monkeypatch, ["yes", True])
    assert generate.codex_label(QUESTION, ["a", "b"]) == [None, True]


# ---- generate.py: the Gemini writer path

def _use_control(monkeypatch, tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"status": "run", "verdict": "use"}))
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "control.json")
    _git(tmp_path, "commit", "-qm", "c")
    monkeypatch.setattr(generate, "WRITER_CONTROL", path)


def _args():
    return argparse.Namespace(writer="gemini", question="core-44", max_usd=1.0)


def test_a_use_control_without_a_gemini_key_is_blocked(monkeypatch, tmp_path, capsys):
    _use_control(monkeypatch, tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    built = []
    monkeypatch.setattr(generate, "gemini_writer", lambda *a: built.append(a))
    assert generate._writer(_args()) is None and built == []
    assert "BLOCKED: GEMINI_API_KEY not in environment" in capsys.readouterr().err


def test_gemini_cases_go_to_their_own_file_never_the_scored_one(monkeypatch, tmp_path):
    _use_control(monkeypatch, tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-a-real-key")
    monkeypatch.setattr(generate, "gemini_writer", lambda *a: "write")
    monkeypatch.setattr(gemini, "today", lambda: dt.date(2026, 10, 1))
    path = generate._writer(_args())[2]
    assert path.name == "core-44.gemini.jsonl" and path != generate.CASES / "core-44.jsonl"


# ---- writer_control.py

@pytest.mark.parametrize("claim, end", [("10", "2026-01-11"), (True, "2026-01-02")])
def test_a_non_int_claimed_days_has_no_anchor_truth(claim, end):
    assert wc.anchor_truth({"class": "dates", "start": "2026-01-01", "end": end, "claimed_days": claim}) is None


@pytest.mark.parametrize("case, cls", [
    ({"state": "x", "label": "yes"}, "normal"), ({"state": 5, "label": True}, "normal"),
    ({"state": "  ", "label": True}, "normal"), ({"state": "x", "label": True}, "arithmetic")])
def test_malformed_control_cases_are_not_well_formed(case, cls):
    assert wc.well_formed(case, cls) is False


def test_a_writer_returning_extra_cases_is_counted_only_up_to_the_request():
    entry = wc.schedule()[2]  # indirection: no anchor fields needed
    reply = json.dumps([{"state": f"case {i}", "label": True, "class": entry["class"]} for i in range(12)])
    st = wc.writer_stats([entry], lambda e: reply, lambda states: [True] * len(states))
    assert (st["requested"], st["returned"], st["missing"], st["agreed"]) == (10, 10, 0, 10)


def test_the_live_control_runs_under_the_writer_cap(monkeypatch, tmp_path):
    class Stop(Exception):
        pass

    seen = []

    def budget(max_usd, price, *rest):
        seen.append(max_usd)
        raise Stop
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-a-real-key")
    monkeypatch.setattr(gemini, "today", lambda: dt.date(2026, 10, 1))
    monkeypatch.setattr(wc, "committed_questions", lambda: [QUESTION])
    monkeypatch.setattr(gemini, "GeminiBudget", budget)
    with pytest.raises(Stop):
        wc.main(tmp_path / "out.json")
    assert seen == [gemini.WRITER_CAP_USD]
