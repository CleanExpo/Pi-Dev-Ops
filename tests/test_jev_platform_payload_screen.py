"""Round 20 P1-JSON-ESCAPING-SENSITIVE-PAYLOAD-BYPASS: a secret after a newline or tab is still refused.

json.dumps writes a newline as backslash-n, so in the serialised text the `n` sits against the secret and the
leading word boundary the patterns need is gone. Every outbound body is now also screened string by string. Each
test proves the JSON screen alone is blind (control), then that nothing is sent. Offline: fakes, no keys.
"""
from __future__ import annotations

import json

import pytest
from jev_scale_support import GOOD, TEMPLATES, FakeGemini, Recorder, budget, ftext, make_repo

from jev_platform import agent, ask, gemini, scout

SECRET = "sk-reviewfixtureabcdefgh"  # the id round 19 reported
HIDDEN = [f"before\n{SECRET}", f"before\t{SECRET}"]


@pytest.mark.parametrize("text", HIDDEN)
def test_the_json_screen_alone_misses_it(text):
    assert ask.sensitive(text) and not ask.sensitive(json.dumps({"q": text}))  # the bypass is live


@pytest.mark.parametrize("text", HIDDEN)
def test_ask_refuses_a_template_hiding_a_secret_after_a_newline_or_tab(tmp_path, text):
    template = {**TEMPLATES["known-issue"], "true": text}
    repo = make_repo(tmp_path, {"src/a.ts": GOOD}, questions={**TEMPLATES, "hidden": template})
    post = Recorder()
    out = ask.ask_files(repo, ["src/a.ts"], ["hidden"], post, budget())
    assert out["blocked"] == "template refused: hidden" and post.calls == []
    assert ask.ask_files(repo, ["src/a.ts"], ["known-issue"], post, budget())["results"]  # control: sent
    assert len(post.calls) == 1


@pytest.mark.parametrize("text", HIDDEN)
def test_scout_refuses_a_body_hiding_a_secret_after_a_newline_or_tab(text):
    post = Recorder()
    assert scout.guarded_send({"state": {"content": text}}, post, budget()) == {"error": "refused: sensitive payload"}
    assert post.calls == []


@pytest.mark.parametrize("text", HIDDEN)
def test_gemini_refuses_before_count_tokens(text):
    fake = FakeGemini([ftext("hi")])
    body = gemini.request_body([{"role": "user", "parts": [{"text": text}]}])
    out = gemini.call(body, "gk-test-not-a-real-key", gemini.GeminiBudget(0.1, dict(gemini.PRICES[gemini.MODEL])),
                      fake, sleep=lambda s: None)
    assert out == {"error": "refused: sensitive payload"} and fake.calls == []


def test_the_agent_catalogue_never_sends_a_sensitive_template_id():
    """The round 19 id reaches Gemini through agent.system_text, one per line after a newline."""
    system = agent.system_text({"files": {"src/a.ts": "0" * 64}, "questions": {SECRET: TEMPLATES["known-issue"]}})
    assert f"\n{SECRET} " in system and not ask.sensitive(json.dumps(system))  # control: the JSON screen is blind
    fake = FakeGemini([ftext("hi")])
    body = gemini.request_body([{"role": "user", "parts": [{"text": "go"}]}], system)
    out = gemini.call(body, "gk-test-not-a-real-key", gemini.GeminiBudget(0.1, dict(gemini.PRICES[gemini.MODEL])),
                      fake, sleep=lambda s: None)
    assert out == {"error": "refused: sensitive payload"} and fake.calls == []
