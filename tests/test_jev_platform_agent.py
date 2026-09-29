"""Offline controls for the Gemini agent runner (jev_platform.agent, PLAN-scale.md rev 5).

A scripted fake Gemini and a fake Jev `post`; no key, no network. The CLI tests drive `main()`.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest
from jev_scale_support import GOOD, FakeGemini, Recorder, budget, fcall, ftext, make_repo, sha

from jev_platform import __main__ as cli
from jev_platform import agent, agent_tools, ask, gemini

KEY = "gk-test-not-a-real-key-7f3a"
FILES = {"src/domain/billing.ts": GOOD, "src/http/routes.ts": "export const r = 1;\n"}
SCOUT = ("ask_jev_files", {"patterns": ["src/domain/*"], "template_ids": ["known-issue"]})


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path, FILES)


def run(repo, replies, jev=None, prompt="p3"):
    fake, jev = FakeGemini(replies), jev or Recorder()
    gem = gemini.GeminiBudget(gemini.RUN_CAP_USD, gemini.price_table(dt.date(2026, 10, 1)))
    ledger = agent.run_agent(repo, prompt, KEY, fake, jev, gem, budget(), sleep=lambda s: None)
    return ledger, fake, jev


def responses_to_model(fake) -> list:
    """Every functionResponse the model was shown, in order."""
    return [p["functionResponse"] for b in fake.generate_bodies() for c in b["contents"] if c["role"] == "user"
            for p in c["parts"] if "functionResponse" in p]


def test_scripted_ask_jev_files_counts_one_jev_call_and_zero_files_read(repo):
    ledger, fake, jev = run(repo, [fcall(SCOUT), ftext("billing.ts admits a TODO")])
    assert ledger["outcome"] == "complete" and ledger["jev_calls"] == 1 and ledger["files_read"] == 0
    assert ledger["questions"] == 1 and len(jev.calls) == 1 and fake.urls() == ["count", "generate"] * 2


def test_ledger_counts_sends_not_model_claims(repo):
    two = ("ask_jev_files", {"patterns": ["src/**"], "template_ids": ["known-issue"]})
    ledger, _, jev = run(repo, [fcall(two), ftext("I made 40 Jev calls and read every file.")])
    assert ledger["jev_calls"] == len(jev.calls) == 2 and ledger["files_read"] == 0
    refused = ("ask_jev_files", {"patterns": ["src/**"], "template_ids": ["no-such-template"]})
    assert run(repo, [fcall(refused), ftext("I asked Jev about every file.")])[0]["jev_calls"] == 0
    assert "40 Jev calls" in agent.render_report(ledger).split("agent summary (unverified):")[1]


def test_projection_has_no_sha256_or_bytes_and_passes_sensitive_while_ledger_keeps_hashes(repo):
    ledger, fake, _ = run(repo, [fcall(SCOUT, ("pick_first_file", {"template_id": "pick-first-for-task",
                                                                   "paths": list(FILES)})), ftext("done")])
    shown = json.dumps(responses_to_model(fake))
    assert sha(GOOD) not in shown and "Math.round" not in shown and not ask.sensitive(shown)
    assert '"template_id": "known-issue"' in shown and sha(GOOD) in json.dumps(ledger["jev_results"])


def test_projection_of_raw_jev_numbers_is_rounded_so_it_passes_sensitive():
    out = {"results": [{"path": "a.ts", "sha256": "ab" * 32, "answers": {"k": {"type": "noul", "noul": 0.1234567890123456}}}],
           "skipped": []}
    shown = json.dumps(agent_tools.project_scout(out))
    assert not ask.sensitive(shown) and "ab" * 32 not in shown and '"noul": 0.1235' in shown


def test_read_file_unapproved_is_refused_without_bytes_and_approved_counts(repo, tmp_path):
    (tmp_path / "src" / "unlisted.ts").write_text("export const hidden = 42;\n")
    ledger, fake, _ = run(repo, [fcall(("read_file", {"path": "src/unlisted.ts"}),
                                       ("read_file", {"path": "src/domain/billing.ts"})), ftext("ok")])
    shown = responses_to_model(fake)
    assert shown[0]["response"] == {"path": "src/unlisted.ts", "refused": "not in approved manifest"}
    assert shown[1]["response"]["content"] == GOOD and ledger["files_read"] == 1 and "hidden" not in json.dumps(shown)


def test_propose_template_never_reaches_jev_and_is_only_echoed_to_gemini(repo):
    mark = "PROPOSALMARK would this file leak"
    proposal = ("propose_template", {"template_id": "new-q", "type": "noul", "question": mark})
    ledger, fake, jev = run(repo, [fcall(proposal, SCOUT), ftext("done")])
    assert all(mark not in json.dumps(b) for b in jev.calls) and ledger["proposals"][0]["question"] == mark
    for body in fake.generate_bodies():
        for c in body["contents"]:
            assert c["role"] == "model" or mark not in json.dumps(c)
    assert responses_to_model(fake)[0]["response"] == {"result": "recorded, not sent"}
    assert "proposed templates (not sent, needs review):" in agent.render_report(ledger)


def test_agent_text_in_tool_arguments_never_reaches_a_jev_body(repo):
    args = {"patterns": ["ZZMARK/**", "src/domain/*"], "template_ids": ["relevant-to-task"]}
    _, _, jev = run(repo, [fcall(("ask_jev_files", args)), ftext("done")])
    assert len(jev.calls) == 1 and "ZZMARK" not in json.dumps(jev.calls)


def test_a_command_argument_is_rejected_by_the_tool_schema(repo):
    call = ("ask_jev", {"paths": list(FILES), "template_ids": ["triage-bundle"], "command": "npm test"})
    ledger, fake, jev = run(repo, [fcall(call), ftext("done")])
    assert responses_to_model(fake)[0]["response"] == {"refused": "unexpected argument: command"} and jev.calls == []
    assert all("command" not in d["parameters"]["properties"] for d in agent_tools.DECLARATIONS[0]["functionDeclarations"])


def test_turn_cap_ends_incomplete(repo):
    ledger, fake, _ = run(repo, [fcall(("read_file", {"path": "src/http/routes.ts"}))] * 13)
    assert ledger["outcome"] == "incomplete: turn cap" and ledger["turns"] == 12 and fake.urls().count("generate") == 12


def test_gemini_500_is_incomplete_with_the_ledger_intact(repo):
    ledger, _, jev = run(repo, [fcall(SCOUT), (500, None)])
    assert ledger["outcome"] == "incomplete: gemini http_500" and ledger["jev_calls"] == 1 == len(jev.calls)


@pytest.mark.parametrize("reply, reason", [
    ({"candidates": []}, "empty candidate"), ({"promptFeedback": {"blockReason": "SAFETY"}}, "safety block"),
    ({"candidates": [{"finishReason": "SAFETY"}]}, "safety block"),
    (fcall(("write_file", {"path": "x"})), "malformed function call"),
    ({"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]}, "empty candidate"),
    ({"candidates": [{"content": {"parts": [{"text": "x"}]}, "finishReason": "MAX_TOKENS"}]}, "output cap reached"),
])
def test_bad_replies_end_the_run_incomplete(repo, reply, reason):
    ledger, _, jev = run(repo, [reply])
    assert ledger["outcome"] == f"incomplete: {reason}" and jev.calls == []


def test_unknown_prompt_in_run_agent_makes_no_request(repo):
    ledger, fake, _ = run(repo, [ftext("x")], prompt="Fix the rounding bug please")
    assert ledger["outcome"] == "incomplete: unknown prompt id" and fake.calls == []


def cli_env(monkeypatch, fake, jev, key=KEY, on=dt.date(2026, 10, 1)):
    for name, value in (("GEMINI_API_KEY", key), ("TYPESAFE_API_KEY", "ts-test-value-0000")):
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gemini, "urllib_post", fake)
    monkeypatch.setattr(gemini, "today", lambda: on)
    monkeypatch.setattr(cli, "http_post", jev)


def test_no_key_is_blocked_first_on_stderr_with_exit_2(monkeypatch, capsys):
    fake, jev = FakeGemini(), Recorder()
    cli_env(monkeypatch, fake, jev, key="")
    assert cli.main(["agent", "--prompt", "x"]) == 2
    assert capsys.readouterr().err.startswith("BLOCKED: GEMINI_API_KEY") and fake.calls == [] == jev.calls


def test_expired_price_table_is_blocked_with_zero_requests(monkeypatch, capsys, repo):
    fake, jev = FakeGemini([ftext("x")]), Recorder()
    cli_env(monkeypatch, fake, jev, on=dt.date(2027, 1, 1))
    assert cli.main(["agent", "--prompt", "p3", "--repo", repo]) == 2
    assert "BLOCKED: price table expired" in capsys.readouterr().err and fake.calls == [] == jev.calls


@pytest.mark.parametrize("prompt", ["nope", "The proration test fails because of rounding."])
def test_unknown_or_free_text_prompt_exits_2_with_zero_requests(monkeypatch, capsys, repo, prompt):
    fake, jev = FakeGemini([ftext("x")]), Recorder()
    cli_env(monkeypatch, fake, jev)
    assert cli.main(["agent", "--prompt", prompt, "--repo", repo]) == 2
    assert "REFUSED" in capsys.readouterr().err and fake.calls == [] == jev.calls


def test_key_never_appears_in_ledger_stdout_or_stderr(monkeypatch, capsys, repo, tmp_path):
    fake, jev = FakeGemini([fcall(SCOUT), ftext("done")]), Recorder()
    cli_env(monkeypatch, fake, jev)
    out_path = tmp_path / "ledger.json"
    assert cli.main(["agent", "--prompt-id", "p3", "--repo", repo, "--ledger", str(out_path)]) == 0
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err + out_path.read_text() and "outcome" in out_path.read_text()
    assert all(h["x-goog-api-key"] == KEY for _, _, h in fake.calls)
