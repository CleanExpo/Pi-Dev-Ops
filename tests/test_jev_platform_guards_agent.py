"""Guard sweep 29/09: every agent.py, agent_tools.py and gemini.py budget guard has a test that fails without it.

Offline only: a scripted fake Gemini and a fake Jev `post`; no key, no network.
"""
from __future__ import annotations

import datetime as dt

import pytest
from jev_scale_support import GOOD, FakeGemini, Recorder, budget, fcall, make_repo

from jev_platform import __main__ as cli
from jev_platform import agent, agent_tools, gemini
from jev_platform import manifest as mf

KEY = "gk-test-not-a-real-key-7f3a"
ON = dt.date(2026, 10, 1)
FILES = {"src/domain/billing.ts": GOOD, "src/http/routes.ts": "export const r = 1;\n"}
USAGE = {"promptTokenCount": 100, "candidatesTokenCount": 20}


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path, FILES)


def run(repo, replies):
    fake = FakeGemini(replies)
    gem = gemini.GeminiBudget(gemini.RUN_CAP_USD, gemini.price_table(ON))
    return agent.run_agent(repo, "p3", KEY, fake, Recorder(), gem, budget(), sleep=lambda s: None), fake


def reply(parts, finish="STOP") -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": USAGE}


# ---- agent.parse_reply

def test_malformed_function_call_finish_ends_the_run_even_with_a_text_part(repo):
    """guard sweep 29/09: MALFORMED_FUNCTION_CALL is refused on the finish reason alone."""
    ledger, _ = run(repo, [reply([{"text": "all done"}], finish="MALFORMED_FUNCTION_CALL")])
    assert ledger["outcome"] == "incomplete: malformed function call" and ledger["summary"] == ""


def test_thought_parts_never_reach_the_summary(repo):
    """guard sweep 29/09: thinking text is excluded; only the answer text is kept."""
    ledger, _ = run(repo, [reply([{"text": "THOUGHTMARK private reasoning", "thought": True}, {"text": "answer"}])])
    assert ledger["outcome"] == "complete" and ledger["summary"] == "answer"


# ---- agent.cmd_agent

def cli_env(monkeypatch, fake, jev, typesafe="ts-test-value-0000"):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    if typesafe:
        monkeypatch.setenv("TYPESAFE_API_KEY", typesafe)
    else:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(gemini, "urllib_post", fake)
    monkeypatch.setattr(gemini, "today", lambda: ON)
    monkeypatch.setattr(cli, "http_post", jev)


def test_max_usd_above_the_run_cap_is_clamped_to_the_run_cap(monkeypatch, repo):
    """guard sweep 29/09: --max-usd 10 still builds a GeminiBudget of RUN_CAP_USD (US$2.50)."""
    seen, real = [], gemini.GeminiBudget

    def spy(max_usd, price, *args, **kwargs):
        seen.append(max_usd)
        return real(max_usd, price, *args, **kwargs)
    cli_env(monkeypatch, FakeGemini([reply([{"text": "done"}])]), Recorder())
    monkeypatch.setattr(gemini, "GeminiBudget", spy)
    assert cli.main(["agent", "--prompt", "p3", "--repo", repo, "--max-usd", "10"]) == 0
    assert seen == [gemini.RUN_CAP_USD] == [2.50]


def test_incomplete_run_exits_1(monkeypatch, capsys, repo):
    """guard sweep 29/09: an incomplete ledger is a non-zero exit, never 0."""
    cli_env(monkeypatch, FakeGemini([(500, None)]), Recorder())
    assert cli.main(["agent", "--prompt", "p3", "--repo", repo]) == 1
    assert "incomplete: gemini http_500" in capsys.readouterr().out


def test_missing_jev_key_is_refused_with_zero_requests(monkeypatch, capsys, repo):
    """guard sweep 29/09: no TYPESAFE_API_KEY means no repo, exit 2, and nothing sent to either model."""
    fake, jev = FakeGemini([fcall(("read_file", {"path": "src/http/routes.ts"})), reply([{"text": "x"}])]), Recorder()
    cli_env(monkeypatch, fake, jev, typesafe="")
    assert cli.main(["agent", "--prompt", "p3", "--repo", repo]) == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err and fake.calls == [] == jev.calls


# ---- agent_tools.args_problem / project_scout

@pytest.fixture
def tool_run(repo):
    post = Recorder()
    return agent_tools.Run(repo, mf.load_manifest(repo)[0], "p3", post, budget()), post


@pytest.mark.parametrize("name, args, refusal", [
    ("read_file", [], "arguments must be an object"),
    ("read_file", {"path": 5}, "argument path must be a string"),
    ("read_file", {}, "argument path must be a string"),
    ("ask_jev_files", {"patterns": [1], "template_ids": ["known-issue"]},
     "argument patterns must be a list of strings"),
])
def test_arguments_outside_the_schema_are_refused_before_any_handler_runs(tool_run, name, args, refusal):
    """guard sweep 29/09: not an object, wrong type, missing or non-string list items are each refused."""
    run, post = tool_run
    assert agent_tools.dispatch(run, name, args) == {"refused": refusal}
    assert post.calls == [] and run.reads == [] and run.results == []


def test_propose_template_may_omit_fields_while_other_tools_may_not(tool_run):
    """guard sweep 29/09: positive control for the missing-argument refusal above."""
    run, _ = tool_run
    assert agent_tools.dispatch(run, "propose_template", {"template_id": "x"}) == {"result": agent_tools.PROPOSED}


def test_a_blocked_scout_is_shown_to_the_model_as_refused_only(tool_run):
    """guard sweep 29/09: a blocked ask_jev_files projects to {"refused": reason}, not an empty file list."""
    run, post = tool_run
    shown = agent_tools.dispatch(run, "ask_jev_files", {"patterns": ["src/**"], "template_ids": ["no-such-template"]})
    assert set(shown) == {"refused"} and shown["refused"] == run.results[0]["result"]["blocked"] and post.calls == []


# ---- gemini.GeminiBudget

def test_generate_attempt_cap_holds_even_when_every_attempt_settles_to_zero():
    """guard sweep 29/09: max_attempts is fixed at start; cheap settled replies never buy a fourth attempt."""
    price = gemini.price_table(ON)
    b = gemini.GeminiBudget(3 * gemini.MAX_OUTPUT_TOKENS * price["out"], price)
    assert b.max_attempts == 3
    for _ in range(3):
        r = b.reserve_generate(0)
        assert r is not None
        b.settle(r, {"promptTokenCount": 0, "candidatesTokenCount": 0}, 0)
    assert b.spent == 0.0 and b.reserve_generate(0) is None and b.attempts == 3


def test_thoughts_without_a_prompt_count_leave_the_carry_unknown():
    """guard sweep 29/09: a thoughtsTokenCount alone is malformed usage, so thinking is unknown, not counted."""
    b = gemini.GeminiBudget(gemini.RUN_CAP_USD, gemini.price_table(ON))
    b.add_thoughts({"thoughtsTokenCount": 5})
    assert b.thoughts_known is False and b.thoughts == 0
    ok = gemini.GeminiBudget(gemini.RUN_CAP_USD, gemini.price_table(ON))
    ok.add_thoughts({**USAGE, "thoughtsTokenCount": 5})
    assert ok.thoughts_known is True and ok.thoughts == 5
